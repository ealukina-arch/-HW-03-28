from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied
from django.conf import settings

# 🆕 ИМПОРТЫ ДЛЯ КЭШИРОВАНИЯ
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.core.cache import cache

from .models import Post, Author, Category, Subscription, ActivationToken
from .filters import PostFilter, ArticleFilter, NewsFilter, QuickPostFilter, CategoryPostFilter
from .forms import PostForm
from .mixins import AuthRequiredMixin, NewsLimitMixin, AuthorRequiredMixin, OwnerRequiredMixin, \
    PermissionRequiredMixinWithMessage
from .services.email_service import EmailService
import logging

logger = logging.getLogger('news.views')


class PermissionRequiredMixinWithMessage(PermissionRequiredMixin):
    permission_denied_message = "У вас недостаточно прав для доступа к этой странице."

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


class AuthorRequiredMixin(UserPassesTestMixin):
    permission_denied_message = "Только авторы могут создавать и редактировать контент."

    def test_func(self):
        return (self.request.user.is_authenticated and
                self.request.user.groups.filter(name='authors').exists())

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


class OwnerRequiredMixin(UserPassesTestMixin):
    """Миксин для проверки владения объектом"""
    permission_denied_message = "Вы можете редактировать только свой собственный контент."

    def test_func(self):
        obj = self.get_object()
        return (obj.author.user == self.request.user or
                self.request.user.is_staff)

    def handle_no_permission(self):
        messages.error(self.request, self.permission_denied_message)
        return redirect('news_list')


# 🔄 ФУНКЦИИ ДЛЯ РАБОТЫ С ПОДПИСКАМИ
@login_required
def subscribe_to_category(request, category_id):
    """Подписка на категорию"""
    logger.info(f"🔔 ЗАПРОС НА ПОДПИСКУ: пользователь={request.user.username}, категория_id={category_id}")

    category = get_object_or_404(Category, id=category_id)
    logger.info(f"📦 Найдена категория: {category.name}")

    subscription, created = Subscription.objects.get_or_create(
        user=request.user,
        category=category
    )

    if created:
        logger.info(f"✅ СОЗДАНА НОВАЯ ПОДПИСКА: {request.user.username} -> {category.name}")
        messages.success(
            request,
            f'✅ Вы успешно подписались на категорию "{category.name}"! '
            f'Теперь вы будете получать уведомления о новых статьях и еженедельные дайджесты.'
        )
    else:
        logger.info(f"ℹ️ ПОДПИСКА УЖЕ СУЩЕСТВУЕТ: {request.user.username} -> {category.name}")
        messages.info(request, f'ℹ️ Вы уже подписаны на категорию "{category.name}"')

    return redirect('category_posts', category_id=category_id)


# 🆕 УЛУЧШЕННОЕ КЭШИРОВАНИЕ СТРАНИЦЫ КАТЕГОРИИ
@cache_page(60 * 5)  # 5 минут
def category_posts(request, category_id):
    """Страница с постами категории с улучшенными фильтрами"""
    logger.info(f"🔔 ЗАПРОС КАТЕГОРИЯ: категория_id={category_id}")

    category = get_object_or_404(Category, id=category_id)

    # Используем улучшенный фильтр для категории
    posts = Post.objects.filter(categories=category).select_related(
        'author__user'
    ).prefetch_related('categories').order_by('-created_at')

    # Применяем фильтры
    filterset = CategoryPostFilter(request.GET, queryset=posts)
    filtered_posts = filterset.qs

    paginator = Paginator(filtered_posts, 12)  # Увеличили количество постов на странице
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    is_subscribed = False
    if request.user.is_authenticated:
        is_subscribed = Subscription.objects.filter(
            user=request.user,
            category=category
        ).exists()

    # Статистика категории
    category_stats = {
        'total_posts': posts.count(),
        'filtered_posts': filtered_posts.count(),
        'subscribers_count': category.subscribers.count(),
        'last_post': posts.first() if posts.exists() else None
    }

    context = {
        'category': category,
        'page_obj': page_obj,
        'is_subscribed': is_subscribed,
        'categories': Category.objects.annotate(posts_count=Count('post')).filter(posts_count__gt=0),
        'filterset': filterset,
        'category_stats': category_stats,
        'active_filters': dict(request.GET)  # Для отображения активных фильтров
    }
    return render(request, 'news/category_posts.html', context)


@login_required
def unsubscribe_from_category(request, category_id):
    """Отписка от категории"""
    logger.info(f"🔔 ЗАПРОС НА ОТПИСКУ: пользователь={request.user.username}, категория_id={category_id}")

    category = get_object_or_404(Category, id=category_id)
    logger.info(f"📦 Найдена категория: {category.name}")

    deleted_count = Subscription.objects.filter(
        user=request.user,
        category=category
    ).delete()[0]

    if deleted_count > 0:
        logger.info(f"❌ ПОДПИСКА УДАЛЕНА: {request.user.username} -> {category.name}")
        messages.success(request, f'❌ Вы отписались от категории "{category.name}"')
    else:
        logger.info(f"⚠️ ПОДПИСКА НЕ НАЙДЕНА: {request.user.username} -> {category.name}")
        messages.warning(request, f'⚠️ Вы не были подписаны на категорию "{category.name}"')

    return redirect('category_posts', category_id=category_id)


@login_required
def my_subscriptions(request):
    """Страница с подписками пользователя"""
    logger.info(f"🔔 ЗАПРОС МОИ ПОДПИСКИ: пользователь={request.user.username}")

    subscriptions = Subscription.objects.filter(user=request.user).select_related('category')
    all_categories = Category.objects.annotate(
        subscribers_count=Count('subscribers'),
        posts_count=Count('post')
    ).order_by('-subscribers_count')

    # Статистика подписок
    subscription_stats = {
        'total': subscriptions.count(),
        'categories_with_posts': all_categories.filter(posts_count__gt=0).count(),
        'recent_posts': Post.objects.filter(
            categories__in=subscriptions.values('category')
        ).order_by('-created_at')[:5]
    }

    context = {
        'subscriptions': subscriptions,
        'categories': all_categories,
        'subscription_stats': subscription_stats
    }
    return render(request, 'news/my_subscriptions.html', context)


# 🔄 ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ АВТОРАМИ
@login_required
def become_author(request):
    """Добавляет пользователя в группу authors"""
    logger.info(f"🔔 ЗАПРОС СТАТЬ АВТОРОМ: пользователь={request.user.username}")

    authors_group, created = Group.objects.get_or_create(name='authors')

    # Назначаем права для группы authors
    content_type = ContentType.objects.get_for_model(Post)
    post_permissions = Permission.objects.filter(content_type=content_type)
    authors_group.permissions.set(post_permissions)

    if not request.user.groups.filter(name='authors').exists():
        request.user.groups.add(authors_group)
        Author.objects.get_or_create(user=request.user)

        logger.info(f"🎉 ПОЛЬЗОВАТЕЛЬ ДОБАВЛЕН В АВТОРЫ: {request.user.username}")
        messages.success(request,
                         '🎉 Поздравляем! Теперь вы автор и можете создавать новости и статьи. '
                         'Перейдите в личный кабинет для управления вашими публикациями.'
                         )
    else:
        logger.info(f"ℹ️ ПОЛЬЗОВАТЕЛЬ УЖЕ АВТОР: {request.user.username}")
        messages.info(request, 'ℹ️ Вы уже являетесь автором.')

    return redirect('author_dashboard')


@login_required
def author_dashboard(request):
    """Дашборд автора с улучшенной статистикой"""
    if not request.user.groups.filter(name='authors').exists():
        messages.error(request, 'Доступно только для авторов')
        return redirect('news_list')

    author = get_object_or_404(Author, user=request.user)

    # Расширенная статистика автора
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))

    # Основная статистика
    posts_today = Post.objects.filter(
        author=author,
        created_at__gte=today_start
    ).count()

    total_posts = Post.objects.filter(author=author).count()
    recent_posts = Post.objects.filter(author=author).select_related(
        'author__user'
    ).prefetch_related('categories').order_by('-created_at')[:10]

    # Дополнительная статистика
    author_stats = {
        'news_count': Post.objects.filter(author=author, post_type=Post.NEWS).count(),
        'articles_count': Post.objects.filter(author=author, post_type=Post.ARTICLE).count(),
        'total_rating': Post.objects.filter(author=author).aggregate(total=Count('rating'))['total'] or 0,
        'avg_rating': Post.objects.filter(author=author).aggregate(avg=Count('rating'))['avg'] or 0,
        'most_popular_post': Post.objects.filter(author=author).order_by('-rating').first(),
        'categories_used': Category.objects.filter(post__author=author).distinct().count()
    }

    context = {
        'author': author,
        'posts_today': posts_today,
        'total_posts': total_posts,
        'recent_posts': recent_posts,
        'news_limit_remaining': max(0, 3 - posts_today),
        'author_stats': author_stats
    }

    return render(request, 'news/author_dashboard.html', context)


# 🔄 ОСНОВНЫЕ КЛАССЫ-ПРЕДСТАВЛЕНИЯ

# 🆕 УЛУЧШЕННЫЙ СПИСОК НОВОСТЕЙ С ФИЛЬТРАМИ
@method_decorator(cache_page(60 * 5), name='dispatch')
class NewsList(ListView):
    model = Post
    template_name = 'news/news_list.html'
    context_object_name = 'news_list'
    paginate_by = 12
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Post.objects.filter(post_type=Post.NEWS).select_related(
            'author__user'
        ).prefetch_related('categories', 'comment_set')

        # Используем улучшенный фильтр для новостей
        self.filterset = NewsFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Статистика для страницы
        total_news = Post.objects.filter(post_type=Post.NEWS).count()
        filtered_count = self.filterset.qs.count()

        context.update({
            'categories': Category.objects.annotate(
                posts_count=Count('post')
            ).filter(posts_count__gt=0),
            'filterset': self.filterset,
            'total_news': total_news,
            'filtered_count': filtered_count,
            'active_filters': dict(self.request.GET),
            'popular_categories': Category.objects.annotate(
                news_count=Count('post', filter=Q(post__post_type=Post.NEWS))
            ).filter(news_count__gt=0).order_by('-news_count')[:5]
        })

        logger.info(
            f"📰 Страница новостей: {filtered_count} из {total_news} новостей, "
            f"активных фильтров: {len(self.request.GET)}"
        )
        return context


# 🆕 СПИСОК СТАТЕЙ С ФИЛЬТРАМИ
@method_decorator(cache_page(60 * 5), name='dispatch')
class ArticleList(ListView):
    model = Post
    template_name = 'news/article_list.html'
    context_object_name = 'articles'
    paginate_by = 12
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Post.objects.filter(post_type=Post.ARTICLE).select_related(
            'author__user'
        ).prefetch_related('categories', 'comment_set')

        # Используем улучшенный фильтр для статей
        self.filterset = ArticleFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        total_articles = Post.objects.filter(post_type=Post.ARTICLE).count()
        filtered_count = self.filterset.qs.count()

        context.update({
            'categories': Category.objects.annotate(
                posts_count=Count('post')
            ).filter(posts_count__gt=0),
            'filterset': self.filterset,
            'total_articles': total_articles,
            'filtered_count': filtered_count,
            'active_filters': dict(self.request.GET),
            'top_authors': Author.objects.annotate(
                articles_count=Count('post', filter=Q(post__post_type=Post.ARTICLE))
            ).filter(articles_count__gt=0).order_by('-articles_count')[:5]
        })

        logger.info(f"📄 Страница статей: {filtered_count} из {total_articles} статей")
        return context


# 🆕 ИНТЕЛЛЕКТУАЛЬНОЕ КЭШИРОВАНИЕ ДЕТАЛЕЙ
class NewsDetail(DetailView):
    model = Post
    template_name = 'news/news_detail.html'
    context_object_name = 'news'

    def get_queryset(self):
        return Post.objects.select_related(
            'author__user'
        ).prefetch_related('categories', 'comment_set', 'comment_set__user')

    def get_cache_key(self):
        """Генерирует уникальный ключ кэша с учетом времени изменения"""
        post = self.get_object()
        return f'post_detail_{post.id}_{post.updated_at.timestamp()}'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        cache_key = self.get_cache_key()

        cached_response = cache.get(cache_key)
        if cached_response:
            logger.info(f"📖 Загружено из кэша: {self.object.title}")
            return cached_response

        context = self.get_context_data(object=self.object)
        response = self.render_to_response(context)

        cache.set(cache_key, response, 60 * 5)
        logger.info(f"📖 Сохранено в кэш: {self.object.title}")

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object

        # Информация о подписках пользователя
        user_subscribed_categories = []
        if self.request.user.is_authenticated:
            user_subscribed_categories = Subscription.objects.filter(
                user=self.request.user,
                category__in=post.categories.all()
            ).values_list('category_id', flat=True)

        # Похожие посты
        similar_posts = Post.objects.filter(
            categories__in=post.categories.all(),
            post_type=post.post_type
        ).exclude(pk=post.pk).select_related(
            'author__user'
        ).prefetch_related('categories').distinct()[:6]

        # Статистика поста
        post_stats = {
            'comments_count': post.comment_set.count(),
            'categories_count': post.categories.count(),
            'reading_time': max(1, len(post.content) // 1800),  # Примерное время чтения в минутах
            'is_recent': post.created_at >= timezone.now() - timezone.timedelta(days=1)
        }

        context.update({
            'categories': Category.objects.all(),
            'user_subscribed_categories': list(user_subscribed_categories),
            'similar_posts': similar_posts,
            'post_stats': post_stats,
            'is_cached': False
        })

        return context


# 🆕 УЛУЧШЕННЫЙ ПОИСК
@method_decorator(cache_page(60 * 2), name='dispatch')
class NewsSearch(ListView):
    model = Post
    template_name = 'news/news_search.html'
    context_object_name = 'news_list'
    paginate_by = 12

    def get_queryset(self):
        queryset = Post.objects.filter(post_type=Post.NEWS).select_related(
            'author__user'
        ).prefetch_related('categories', 'comment_set')

        # Используем полный фильтр для поиска
        self.filterset = PostFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        search_query = self.request.GET.get('search', '')
        total_results = self.filterset.qs.count()

        context.update({
            'filterset': self.filterset,
            'categories': Category.objects.annotate(posts_count=Count('post')).filter(posts_count__gt=0),
            'search_query': search_query,
            'total_results': total_results,
            'active_filters': dict(self.request.GET),
            'search_suggestions': self.get_search_suggestions(search_query) if search_query else []
        })

        logger.info(f"🔍 Поиск новостей: '{search_query}' - найдено {total_results} результатов")
        return context

    def get_search_suggestions(self, query):
        """Возвращает предложения для поиска"""
        if len(query) < 3:
            return []

        return Post.objects.filter(
            Q(title__icontains=query) | Q(content__icontains=query),
            post_type=Post.NEWS
        ).values_list('title', flat=True).distinct()[:5]


# 🔄 CRUD ПРЕДСТАВЛЕНИЯ ДЛЯ НОВОСТЕЙ (остаются без значительных изменений)
class NewsCreate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, NewsLimitMixin,
                 CreateView):
    form_class = PostForm
    model = Post
    template_name = 'news/news_edit.html'
    permission_required = 'news.add_post'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        post = form.save(commit=False)
        post.post_type = Post.NEWS
        author, created = Author.objects.get_or_create(user=self.request.user)
        post.author = author

        response = super().form_valid(form)
        form.save_m2m()

        # Отправляем уведомления
        logger.info(f"📝 Новость создана, отправляем уведомления для ID: {self.object.pk}")
        self.object.send_notifications_to_subscribers()

        # Очистка кэша
        self.clear_related_caches()
        return response

    def clear_related_caches(self):
        cache.delete_pattern('*home_page*')
        cache.delete_pattern('*news_list*')
        for category in self.object.categories.all():
            cache.delete_pattern(f'*category_{category.id}*')
        logger.info(f"🧹 Очищен кэш для новой новости: {self.object.title}")

    def get_success_url(self):
        messages.success(self.request, '✅ Новость успешно создана! Подписчики получат уведомления.')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Создание новости'
        context['categories'] = Category.objects.all()

        if hasattr(self.request.user, 'author'):
            news_count = self.request.user.author.get_news_count_today()
            context.update({
                'news_count_today': news_count,
                'news_remaining': max(0, 3 - news_count)
            })
        return context


# 🔄 ОСТАЛЬНЫЕ CRUD ПРЕДСТАВЛЕНИЯ (NewsUpdate, NewsDelete, ArticleCreate, ArticleUpdate, ArticleDelete)
# остаются без значительных изменений, аналогично NewsCreate

class NewsUpdate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                 UpdateView):
    form_class = PostForm
    model = Post
    template_name = 'news/news_edit.html'
    permission_required = 'news.change_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.NEWS)

    def form_valid(self, form):
        response = super().form_valid(form)
        self.clear_post_cache()
        return response

    def clear_post_cache(self):
        cache_key = f'post_detail_{self.object.id}_*'
        cache.delete_pattern(cache_key)
        logger.info(f"🧹 Очищен кэш для обновленной новости: {self.object.title}")

    def get_success_url(self):
        messages.success(self.request, '✅ Новость успешно обновлена!')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактирование новости'
        context['categories'] = Category.objects.all()
        return context


class NewsDelete(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                 DeleteView):
    model = Post
    template_name = 'news/news_delete.html'
    success_url = reverse_lazy('news_list')
    permission_required = 'news.delete_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.NEWS)

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.clear_post_cache()
        messages.success(request, '✅ Новость успешно удалена!')
        return super().delete(request, *args, **kwargs)

    def clear_post_cache(self):
        cache_key = f'post_detail_{self.object.id}_*'
        cache.delete_pattern(cache_key)
        logger.info(f"🧹 Очищен кэш для удаленной новости: {self.object.title}")


class ArticleCreate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, CreateView):
    form_class = PostForm
    model = Post
    template_name = 'news/article_edit.html'
    permission_required = 'news.add_post'

    def form_valid(self, form):
        post = form.save(commit=False)
        post.post_type = Post.ARTICLE
        author, created = Author.objects.get_or_create(user=self.request.user)
        post.author = author
        response = super().form_valid(form)
        form.save_m2m()

        logger.info(f"📄 Статья создана: {self.object.title}")
        self.clear_related_caches()
        return response

    def clear_related_caches(self):
        for category in self.object.categories.all():
            cache.delete_pattern(f'*category_{category.id}*')
        logger.info(f"🧹 Очищен кэш для новой статьи: {self.object.title}")

    def get_success_url(self):
        messages.success(self.request, '✅ Статья успешно создана!')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Создание статьи'
        context['categories'] = Category.objects.all()
        return context


class ArticleUpdate(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                    UpdateView):
    form_class = PostForm
    model = Post
    template_name = 'news/article_edit.html'
    permission_required = 'news.change_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.ARTICLE)

    def form_valid(self, form):
        response = super().form_valid(form)
        self.clear_post_cache()
        return response

    def clear_post_cache(self):
        cache_key = f'post_detail_{self.object.id}_*'
        cache.delete_pattern(cache_key)
        logger.info(f"🧹 Очищен кэш для обновленной статьи: {self.object.title}")

    def get_success_url(self):
        messages.success(self.request, '✅ Статья успешно обновлена!')
        return reverse_lazy('news_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактирование статьи'
        context['categories'] = Category.objects.all()
        return context


class ArticleDelete(PermissionRequiredMixinWithMessage, AuthRequiredMixin, AuthorRequiredMixin, OwnerRequiredMixin,
                    DeleteView):
    model = Post
    template_name = 'news/article_delete.html'
    success_url = reverse_lazy('news_list')
    permission_required = 'news.delete_post'

    def get_queryset(self):
        return Post.objects.filter(post_type=Post.ARTICLE)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.clear_post_cache()
        messages.success(request, '✅ Статья успешно удалена!')
        return super().delete(request, *args, **kwargs)

    def clear_post_cache(self):
        cache_key = f'post_detail_{self.object.id}_*'
        cache.delete_pattern(cache_key)
        logger.info(f"🧹 Очищен кэш для удаленной статьи: {self.object.title}")


# 🔄 АКТИВАЦИЯ АККАУНТА (без изменений)
class ActivationView(TemplateView):
    template_name = 'accounts/activation.html'

    def get(self, request, token, *args, **kwargs):
        context = self.get_context_data(**kwargs)

        try:
            activation_token = ActivationToken.objects.select_related('user').get(token=token)

            if activation_token.is_expired():
                context['status'] = 'expired'
                context['message'] = 'Ссылка активации устарела. Пожалуйста, запросите новую.'
            elif activation_token.activated:
                context['status'] = 'already_activated'
                context['message'] = 'Аккаунт уже был активирован ранее.'
            else:
                activation_token.activated = True
                activation_token.save()
                user = activation_token.user
                user.is_active = True
                user.save()

                context['status'] = 'success'
                context['message'] = '✅ Аккаунт успешно активирован! Теперь вы можете войти в систему.'
                context['username'] = user.username

                logger.info(f"✅ Аккаунт активирован: {user.username}")

        except ActivationToken.DoesNotExist:
            context['status'] = 'invalid'
            context['message'] = 'Неверная ссылка активации. Пожалуйста, проверьте правильность ссылки.'

        return self.render_to_response(context)


@login_required
def resend_activation_email(request):
    """
    Повторная отправка письма активации
    """
    try:
        activation_token = ActivationToken.objects.get(user=request.user)

        if activation_token.activated:
            messages.info(request, '✅ Ваш аккаунт уже активирован.')
        elif activation_token.is_expired():
            activation_token.delete()
            new_token = ActivationToken.create_token(request.user)
            activation_url = f"{settings.SITE_URL}/accounts/activate/{new_token.token}/"
            EmailService.send_welcome_email(request.user, activation_url)
            messages.success(request, '📧 Новое письмо активации отправлено на ваш email.')
        else:
            activation_url = f"{settings.SITE_URL}/accounts/activate/{activation_token.token}/"
            EmailService.send_welcome_email(request.user, activation_url)
            messages.success(request, '📧 Письмо активации отправлено на ваш email.')

    except ActivationToken.DoesNotExist:
        new_token = ActivationToken.create_token(request.user)
        activation_url = f"{settings.SITE_URL}/accounts/activate/{new_token.token}/"
        EmailService.send_welcome_email(request.user, activation_url)
        messages.success(request, '📧 Письмо активации отправлено на ваш email.')

    return redirect('profile')


# 🔄 УЛУЧШЕННАЯ ГЛАВНАЯ СТРАНИЦА
@method_decorator(cache_page(60), name='dispatch')
class HomePageView(ListView):
    """Главная страница с улучшенной статистикой"""
    model = Post
    template_name = 'news/home.html'
    context_object_name = 'latest_news'
    paginate_by = 8

    def get_queryset(self):
        # Используем быстрый фильтр для главной страницы
        queryset = Post.objects.filter(post_type=Post.NEWS).select_related(
            'author__user'
        ).prefetch_related('categories').order_by('-created_at')[:20]

        self.filterset = QuickPostFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Статистика для главной страницы
        site_stats = {
            'total_news': Post.objects.filter(post_type=Post.NEWS).count(),
            'total_articles': Post.objects.filter(post_type=Post.ARTICLE).count(),
            'total_categories': Category.objects.count(),
            'total_authors': Author.objects.count(),
            'popular_categories': Category.objects.annotate(
                post_count=Count('post')
            ).filter(post_count__gt=0).order_by('-post_count')[:6],
            'recent_authors': Author.objects.annotate(
                post_count=Count('post')
            ).filter(post_count__gt=0).order_by('-post_count')[:4]
        }

        context.update({
            'categories': Category.objects.annotate(
                posts_count=Count('post')
            ).filter(posts_count__gt=0)[:8],
            'filterset': self.filterset,
            'site_stats': site_stats,
            'trending_posts': Post.objects.select_related('author__user').prefetch_related('categories').order_by(
                '-rating')[:3]
        })
        return context


@login_required
def profile(request):
    """Профиль пользователя с улучшенной статистикой"""
    user = request.user

    # Базовая информация
    context = {
        'is_author': user.groups.filter(name='authors').exists(),
        'subscriptions_count': Subscription.objects.filter(user=user).count(),
        'categories': Category.objects.annotate(posts_count=Count('post')).filter(posts_count__gt=0),
    }

    # Расширенная статистика для авторов
    if hasattr(user, 'author'):
        author = user.author
        author_posts = Post.objects.filter(author=author)

        author_stats = {
            'posts_count': author_posts.count(),
            'news_count': author_posts.filter(post_type=Post.NEWS).count(),
            'articles_count': author_posts.filter(post_type=Post.ARTICLE).count(),
            'total_rating': author_posts.aggregate(total=Count('rating'))['total'] or 0,
            'news_today': author.get_news_count_today(),
            'most_popular_post': author_posts.order_by('-rating').first(),
            'last_post': author_posts.order_by('-created_at').first()
        }

        context.update({
            'author': author,
            'author_stats': author_stats
        })

    return render(request, 'accounts/profile.html', context)