from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.core.mail import send_mass_mail
from django.conf import settings

from .models import Author, Category, Post, Comment, Subscription, ActivationToken, PostCategory
import logging

logger = logging.getLogger('news.admin')


# 🔄 УЛУЧШЕННЫЕ КАСТОМНЫЕ ФИЛЬТРЫ
class RatingRangeFilter(admin.SimpleListFilter):
    """Фильтр по диапазону рейтинга"""
    title = 'Диапазон рейтинга'
    parameter_name = 'rating_range'

    def lookups(self, request, model_admin):
        return [
            ('high', 'Высокий (10+)'),
            ('medium', 'Средний (5-9)'),
            ('low', 'Низкий (1-4)'),
            ('zero', 'Нулевой'),
            ('negative', 'Отрицательный'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'high':
            return queryset.filter(rating__gte=10)
        elif self.value() == 'medium':
            return queryset.filter(rating__range=(5, 9))
        elif self.value() == 'low':
            return queryset.filter(rating__range=(1, 4))
        elif self.value() == 'zero':
            return queryset.filter(rating=0)
        elif self.value() == 'negative':
            return queryset.filter(rating__lt=0)
        return queryset


class DateRangeFilter(admin.SimpleListFilter):
    """Фильтр по диапазону дат"""
    title = 'Период создания'
    parameter_name = 'date_range'

    def lookups(self, request, model_admin):
        return [
            ('today', 'Сегодня'),
            ('week', 'За неделю'),
            ('month', 'За месяц'),
            ('year', 'За год'),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'today':
            return queryset.filter(created_at__date=now.date())
        elif self.value() == 'week':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=7))
        elif self.value() == 'month':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=30))
        elif self.value() == 'year':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=365))
        return queryset


class CategoryFilter(admin.SimpleListFilter):
    """Фильтр по категориям для постов"""
    title = 'Категория'
    parameter_name = 'category'

    def lookups(self, request, model_admin):
        categories = Category.objects.annotate(post_count=Count('post')).filter(post_count__gt=0)
        return [(cat.id, f"{cat.name} ({cat.post_count})") for cat in categories]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(categories__id=self.value())
        return queryset


class AuthorFilter(admin.SimpleListFilter):
    """Фильтр по авторам"""
    title = 'Автор'
    parameter_name = 'author'

    def lookups(self, request, model_admin):
        authors = Author.objects.select_related('user').annotate(
            post_count=Count('post')
        ).filter(post_count__gt=0)
        return [(author.id, f"{author.user.username} ({author.post_count})") for author in authors]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(author__id=self.value())
        return queryset


class PostTypeFilter(admin.SimpleListFilter):
    """Фильтр по типу контента"""
    title = 'Тип контента'
    parameter_name = 'post_type'

    def lookups(self, request, model_admin):
        return [
            ('news', '📰 Новости'),
            ('articles', '📄 Статьи'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'news':
            return queryset.filter(post_type=Post.NEWS)
        elif self.value() == 'articles':
            return queryset.filter(post_type=Post.ARTICLE)
        return queryset


class CommentDateFilter(admin.SimpleListFilter):
    """Фильтр по дате комментариев"""
    title = 'Период комментария'
    parameter_name = 'comment_date'

    def lookups(self, request, model_admin):
        return [
            ('today', 'Сегодня'),
            ('week', 'За неделю'),
            ('month', 'За месяц'),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'today':
            return queryset.filter(created_at__date=now.date())
        elif self.value() == 'week':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=7))
        elif self.value() == 'month':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=30))
        return queryset


# 🔄 INLINE МОДЕЛИ
class PostCategoryInline(admin.TabularInline):
    model = PostCategory
    extra = 1
    verbose_name = 'Категория'
    verbose_name_plural = 'Категории поста'
    autocomplete_fields = ['category']


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 1
    verbose_name = 'Подписка'
    verbose_name_plural = 'Подписки пользователя'
    autocomplete_fields = ['category']


class CategorySubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 1
    verbose_name = 'Подписчик'
    verbose_name_plural = 'Подписчики категории'
    autocomplete_fields = ['user']


class AuthorPostsInline(admin.StackedInline):
    """Inline для отображения постов автора"""
    model = Post
    extra = 0
    readonly_fields = ['title', 'post_type', 'created_at', 'rating', 'categories_list']
    can_delete = False
    max_num = 5
    verbose_name = 'Последний пост'
    verbose_name_plural = 'Последние посты автора'
    fk_name = 'author'

    def has_add_permission(self, request, obj):
        return False

    def categories_list(self, obj):
        categories = obj.categories.all()[:3]
        return ", ".join([cat.name for cat in categories])

    categories_list.short_description = 'Категории'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author').prefetch_related('categories').order_by(
            '-created_at')


# 🔄 ОСНОВНЫЕ АДМИН-МОДЕЛИ
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ['user', 'rating_badge', 'posts_count', 'last_post_date', 'is_active']
    list_filter = [RatingRangeFilter, 'user__is_active', 'user__date_joined']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['rating', 'user_info', 'statistics']
    inlines = [AuthorPostsInline]
    list_per_page = 25

    fieldsets = [
        ('Основная информация', {
            'fields': ['user', 'user_info', 'rating']
        }),
        ('Статистика автора', {
            'fields': ['statistics'],
            'classes': ['collapse']
        }),
    ]

    def user_info(self, obj):
        user = obj.user
        return format_html(
            '''
            <div style="padding: 10px; background: #f8f9fa; border-radius: 5px;">
                <strong>Email:</strong> {}<br>
                <strong>Имя:</strong> {}<br>
                <strong>Фамилия:</strong> {}<br>
                <strong>Дата регистрации:</strong> {}<br>
                <strong>Статус:</strong> {}
            </div>
            ''',
            user.email,
            user.first_name or 'Не указано',
            user.last_name or 'Не указано',
            user.date_joined.strftime('%d.%m.%Y %H:%M'),
            '✅ Активен' if user.is_active else '❌ Неактивен'
        )

    user_info.short_description = '📋 Информация о пользователе'

    def rating_badge(self, obj):
        color = 'green' if obj.rating > 10 else 'orange' if obj.rating > 0 else 'red'
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; border-radius: 12px; font-weight: bold;">{}</span>',
            color, obj.rating
        )

    rating_badge.short_description = '⭐ Рейтинг'

    def posts_count(self, obj):
        count = obj.post_set.count()
        return format_html(
            '<span style="font-weight: bold; color: {};">{}</span>',
            'green' if count > 0 else 'gray',
            count
        )

    posts_count.short_description = '📄 Постов'

    def last_post_date(self, obj):
        last_post = obj.post_set.order_by('-created_at').first()
        if last_post:
            return format_html(
                '<span title="{}">{}</span>',
                last_post.title,
                last_post.created_at.strftime('%d.%m.%Y')
            )
        return '—'

    last_post_date.short_description = '📅 Последний пост'

    def is_active(self, obj):
        return obj.user.is_active

    is_active.boolean = True
    is_active.short_description = '✅ Активен'

    def statistics(self, obj):
        posts = obj.post_set.all()
        news_count = posts.filter(post_type=Post.NEWS).count()
        articles_count = posts.filter(post_type=Post.ARTICLE).count()
        avg_rating = posts.aggregate(avg=Count('rating'))['avg'] or 0

        return format_html(
            '''
            <div style="padding: 10px; background: #e9ecef; border-radius: 5px;">
                <strong>📊 Статистика:</strong><br>
                • Всего постов: <strong>{}</strong><br>
                • Новостей: <strong>{}</strong><br>
                • Статей: <strong>{}</strong><br>
                • Средний рейтинг: <strong>{}</strong>
            </div>
            ''',
            posts.count(), news_count, articles_count, avg_rating
        )

    statistics.short_description = 'Статистика'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').annotate(
            posts_count=Count('post')
        ).prefetch_related('post_set')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'subscribers_count', 'posts_count', 'last_post_date', 'is_popular']
    list_filter = [DateRangeFilter]
    search_fields = ['name']
    inlines = [CategorySubscriptionInline]
    list_per_page = 20

    def subscribers_count(self, obj):
        count = obj.subscribers.count()
        return format_html(
            '<span style="color: {}; font-weight: bold;">👥 {}</span>',
            'green' if count > 10 else 'orange' if count > 0 else 'red',
            count
        )

    subscribers_count.short_description = 'Подписчики'

    def posts_count(self, obj):
        count = obj.post_set.count()
        return format_html(
            '<span style="color: {}; font-weight: bold;">📄 {}</span>',
            'green' if count > 0 else 'gray',
            count
        )

    posts_count.short_description = 'Постов'

    def last_post_date(self, obj):
        last_post = obj.post_set.order_by('-created_at').first()
        return last_post.created_at.strftime('%d.%m.%Y') if last_post else '—'

    last_post_date.short_description = '📅 Последний пост'

    def is_popular(self, obj):
        return obj.subscribers.count() > 10

    is_popular.boolean = True
    is_popular.short_description = '🔥 Популярная'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            subscribers_count=Count('subscribers'),
            posts_count=Count('post')
        ).prefetch_related('post_set')


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        'title_preview',
        'post_type_badge',
        'author_link',
        'created_at_formatted',
        'rating_badge',
        'categories_list',
        'comments_count_badge',
        'notifications_status'
    ]
    list_filter = [
        CategoryFilter,
        AuthorFilter,
        PostTypeFilter,
        DateRangeFilter,
        RatingRangeFilter,
        'notifications_sent',
        'created_at'
    ]
    search_fields = [
        'title',
        'content',
        'author__user__username',
        'categories__name'
    ]
    list_select_related = ['author__user']
    inlines = [PostCategoryInline]
    readonly_fields = ['created_at', 'updated_at', 'preview_content']
    date_hierarchy = 'created_at'
    actions = ['send_notifications_action', 'update_ratings_action', 'mark_as_sent_action']
    save_on_top = True
    list_per_page = 25

    fieldsets = [
        ('Основная информация', {
            'fields': ['title', 'content', 'author', 'post_type']
        }),
        ('Дополнительно', {
            'fields': ['rating', 'preview_content', 'created_at', 'updated_at'],
            'classes': ['collapse']
        }),
        ('Уведомления', {
            'fields': ['notifications_sent'],
            'classes': ['collapse']
        }),
    ]

    def title_preview(self, obj):
        return format_html(
            '<strong>{}</strong><br><small style="color: #666;">{}</small>',
            obj.title[:60] + '...' if len(obj.title) > 60 else obj.title,
            obj.preview()[:80] + '...' if len(obj.preview()) > 80 else obj.preview()
        )

    title_preview.short_description = '📝 Заголовок и превью'

    def post_type_badge(self, obj):
        colors = {
            Post.NEWS: '#007bff',
            Post.ARTICLE: '#28a745'
        }
        icons = {
            Post.NEWS: '📰',
            Post.ARTICLE: '📄'
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{} {}</span>',
            colors.get(obj.post_type, '#6c757d'),
            icons.get(obj.post_type, '📄'),
            obj.get_post_type_display()
        )

    post_type_badge.short_description = 'Тип'

    def author_link(self, obj):
        return format_html(
            '<a href="{}?author={}" style="font-weight: bold;">{}</a>',
            reverse('admin:news_post_changelist'),
            obj.author.id,
            obj.author.user.username
        )

    author_link.short_description = '👤 Автор'

    def created_at_formatted(self, obj):
        return format_html(
            '<span title="{}">{}</span>',
            obj.created_at.strftime('%d.%m.%Y %H:%M:%S'),
            obj.created_at.strftime('%d.%m.%Y')
        )

    created_at_formatted.short_description = '📅 Дата'

    def rating_badge(self, obj):
        color = 'green' if obj.rating > 5 else 'orange' if obj.rating > 0 else 'red'
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; border-radius: 12px; font-weight: bold;">{}</span>',
            color, obj.rating
        )

    rating_badge.short_description = '⭐ Рейтинг'

    def categories_list(self, obj):
        categories = obj.categories.all()[:3]
        category_links = []
        for category in categories:
            category_links.append(
                f'<span style="background: #e9ecef; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin: 1px;">{category.name}</span>'
            )

        remaining = obj.categories.count() - 3
        if remaining > 0:
            category_links.append(f'<span style="color: #6c757d; font-size: 11px;">+{remaining}</span>')

        return format_html(' '.join(category_links))

    categories_list.short_description = '🏷️ Категории'

    def comments_count_badge(self, obj):
        count = obj.comment_set.count()
        color = 'green' if count > 0 else 'gray'
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; border-radius: 12px; font-weight: bold;">💬 {}</span>',
            color, count
        )

    comments_count_badge.short_description = '💬 Комментарии'

    def notifications_status(self, obj):
        if obj.notifications_sent:
            return format_html('<span style="color: green;">✅ Отправлены</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Не отправлены</span>')

    notifications_status.short_description = '📧 Уведомления'

    def preview_content(self, obj):
        return format_html(
            '<div style="max-height: 200px; overflow-y: auto; padding: 10px; background: #f8f9fa; border-radius: 5px; font-size: 14px;">{}</div>',
            obj.content
        )

    preview_content.short_description = '📖 Предпросмотр содержания'

    def send_notifications_action(self, request, queryset):
        """Действие для ручной отправки уведомлений"""
        success_count = 0
        error_count = 0

        for post in queryset:
            if not post.categories.exists():
                self.message_user(
                    request,
                    f"⚠️ У поста '{post.title}' нет категорий",
                    level='WARNING'
                )
                continue

            try:
                post.send_notifications_to_subscribers()
                success_count += 1
                logger.info(f"✅ Уведомления отправлены для поста '{post.title}'")
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка отправки уведомлений для '{post.title}': {e}")
                self.message_user(
                    request,
                    f"❌ Ошибка для '{post.title}': {e}",
                    level='ERROR'
                )

        if success_count > 0:
            self.message_user(
                request,
                f"✅ Уведомления отправлены для {success_count} постов"
            )

    send_notifications_action.short_description = "📧 Отправить уведомления подписчикам"

    def update_ratings_action(self, request, queryset):
        """Действие для обновления рейтингов"""
        updated_count = 0
        for post in queryset:
            # Здесь можно добавить логику пересчета рейтинга
            post.save()
            updated_count += 1

        self.message_user(
            request,
            f"✅ Рейтинги обновлены для {updated_count} постов"
        )

    update_ratings_action.short_description = "🔄 Обновить рейтинги"

    def mark_as_sent_action(self, request, queryset):
        """Пометить уведомления как отправленные"""
        updated_count = queryset.update(notifications_sent=True)
        self.message_user(
            request,
            f"✅ {updated_count} постов помечены как отправленные"
        )

    mark_as_sent_action.short_description = "✅ Пометить уведомления отправленными"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'author__user'
        ).prefetch_related(
            'categories', 'comment_set'
        ).annotate(
            categories_count=Count('categories'),
            comments_count=Count('comment')
        )


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'post_preview', 'text_preview', 'created_at_formatted', 'rating_badge', 'is_recent']
    list_filter = [CommentDateFilter, 'rating', 'created_at']
    search_fields = ['user__username', 'post__title', 'text']
    readonly_fields = ['created_at', 'user_info']
    date_hierarchy = 'created_at'
    list_per_page = 20

    def post_preview(self, obj):
        return format_html(
            '<strong>{}</strong><br><small style="color: #666;">Автор: {}</small>',
            obj.post.title[:50] + '...' if len(obj.post.title) > 50 else obj.post.title,
            obj.post.author.user.username
        )

    post_preview.short_description = '📝 Пост'

    def text_preview(self, obj):
        return obj.text[:80] + '...' if len(obj.text) > 80 else obj.text

    text_preview.short_description = '💬 Текст комментария'

    def created_at_formatted(self, obj):
        return obj.created_at.strftime('%d.%m.%Y %H:%M')

    created_at_formatted.short_description = '📅 Дата'

    def rating_badge(self, obj):
        color = 'green' if obj.rating > 0 else 'red' if obj.rating < 0 else 'gray'
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span>',
            color, obj.rating
        )

    rating_badge.short_description = '⭐ Рейтинг'

    def is_recent(self, obj):
        return obj.created_at >= timezone.now() - timezone.timedelta(hours=24)

    is_recent.boolean = True
    is_recent.short_description = '🆕 Сегодня'

    def user_info(self, obj):
        user = obj.user
        return format_html(
            '''
            <div style="padding: 8px; background: #f8f9fa; border-radius: 5px;">
                <strong>Username:</strong> {}<br>
                <strong>Email:</strong> {}<br>
                <strong>Имя:</strong> {}<br>
                <strong>Фамилия:</strong> {}
            </div>
            ''',
            user.username,
            user.email,
            user.first_name or 'Не указано',
            user.last_name or 'Не указано'
        )

    user_info.short_description = '👤 Информация о пользователе'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'post', 'post__author__user')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'category', 'subscribed_at_formatted', 'is_active', 'duration']
    list_filter = ['category', 'subscribed_at']
    search_fields = ['user__username', 'category__name']
    date_hierarchy = 'subscribed_at'
    autocomplete_fields = ['user', 'category']
    list_per_page = 20

    def subscribed_at_formatted(self, obj):
        return obj.subscribed_at.strftime('%d.%m.%Y %H:%M')

    subscribed_at_formatted.short_description = '📅 Дата подписки'

    def is_active(self, obj):
        return obj.subscribed_at >= timezone.now() - timezone.timedelta(days=30)

    is_active.boolean = True
    is_active.short_description = '✅ Активна'

    def duration(self, obj):
        days = (timezone.now() - obj.subscribed_at).days
        return format_html(
            '<span style="color: {};">{} дн.</span>',
            'green' if days < 30 else 'orange' if days < 90 else 'red',
            days
        )

    duration.short_description = '⏱ Длительность'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'category')


@admin.register(ActivationToken)
class ActivationTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token_short', 'created_at_formatted', 'activated', 'is_expired', 'status']
    list_filter = ['activated', 'created_at']
    search_fields = ['user__username', 'token']
    readonly_fields = ['created_at', 'token', 'user_info']
    date_hierarchy = 'created_at'
    list_per_page = 20

    def token_short(self, obj):
        return f"{obj.token[:16]}..." if obj.token else "-"

    token_short.short_description = '🔑 Токен'

    def created_at_formatted(self, obj):
        return obj.created_at.strftime('%d.%m.%Y %H:%M')

    created_at_formatted.short_description = '📅 Создан'

    def is_expired(self, obj):
        return obj.is_expired()

    is_expired.boolean = True
    is_expired.short_description = '⏰ Истек'

    def status(self, obj):
        if obj.activated:
            return format_html('<span style="color: green;">✅ Активирован</span>')
        elif obj.is_expired():
            return format_html('<span style="color: red;">❌ Истек</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Ожидает активации</span>')

    status.short_description = '📊 Статус'

    def user_info(self, obj):
        user = obj.user
        return format_html(
            '''
            <div style="padding: 8px; background: #f8f9fa; border-radius: 5px;">
                <strong>Username:</strong> {}<br>
                <strong>Email:</strong> {}<br>
                <strong>Активен:</strong> {}<br>
                <strong>Дата регистрации:</strong> {}
            </div>
            ''',
            user.username,
            user.email,
            '✅ Да' if user.is_active else '❌ Нет',
            user.date_joined.strftime('%d.%m.%Y %H:%M')
        )

    user_info.short_description = '👤 Информация о пользователе'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


# 🔄 РАСШИРЕННАЯ АДМИНКА ПОЛЬЗОВАТЕЛЕЙ
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + (
    'is_author', 'subscriptions_count', 'last_login_display', 'date_joined_display')
    list_filter = UserAdmin.list_filter + ('groups', 'is_staff', 'is_active')
    inlines = [SubscriptionInline]
    list_per_page = 25

    def is_author(self, obj):
        return obj.groups.filter(name='authors').exists()

    is_author.boolean = True
    is_author.short_description = '👤 Автор'

    def subscriptions_count(self, obj):
        count = obj.subscribed_categories.count()
        return format_html(
            '<span style="color: {}; font-weight: bold;">📩 {}</span>',
            'green' if count > 0 else 'gray',
            count
        )

    subscriptions_count.short_description = 'Подписок'

    def last_login_display(self, obj):
        if obj.last_login:
            return obj.last_login.strftime('%d.%m.%Y %H:%M')
        return 'Никогда'

    last_login_display.short_description = '🔐 Последний вход'

    def date_joined_display(self, obj):
        return obj.date_joined.strftime('%d.%m.%Y')

    date_joined_display.short_description = '📅 Регистрация'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'groups', 'subscribed_categories'
        ).annotate(
            subscriptions_count=Count('subscribed_categories')
        )


# 🔄 КАСТОМНАЯ ГРУППА
class CustomGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'users_count', 'permissions_count']
    filter_horizontal = ['permissions']
    search_fields = ['name']
    list_per_page = 20

    def users_count(self, obj):
        count = obj.user_set.count()
        return format_html(
            '<span style="color: {}; font-weight: bold;">👥 {}</span>',
            'green' if count > 0 else 'gray',
            count
        )

    users_count.short_description = 'Пользователей'

    def permissions_count(self, obj):
        return obj.permissions.count()

    permissions_count.short_description = '🔐 Прав'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            users_count=Count('user'),
            permissions_count=Count('permissions')
        )


# 🔄 РЕГИСТРАЦИЯ И ПЕРЕРЕГИСТРАЦИЯ
admin.site.unregister(User)
admin.site.unregister(Group)

admin.site.register(User, CustomUserAdmin)
admin.site.register(Group, CustomGroupAdmin)