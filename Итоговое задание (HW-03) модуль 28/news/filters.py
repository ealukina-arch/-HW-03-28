import django_filters
from django import forms
from django.utils import timezone
from django.db.models import Q
from .models import Post, Category, Author


class PostFilter(django_filters.FilterSet):
    # 🔍 Поиск по тексту
    search = django_filters.CharFilter(
        method='filter_search',
        label='🔍 Поиск по тексту',
        widget=forms.TextInput(attrs={
            'placeholder': 'Введите название или текст...',
            'class': 'form-control',
            'style': 'max-width: 300px;'
        })
    )

    # 📂 Фильтр по категориям (множественный выбор)
    categories = django_filters.ModelMultipleChoiceFilter(
        field_name='categories',
        queryset=Category.objects.all(),
        label='📂 Категории',
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'category-filter'
        })
    )

    # 👤 Фильтр по авторам
    author = django_filters.ModelChoiceFilter(
        field_name='author',
        queryset=Author.objects.select_related('user').all(),
        label='👤 Автор',
        method='filter_author',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'style': 'max-width: 250px;'
        })
    )

    # 📅 Фильтр по дате создания
    date_range = django_filters.ChoiceFilter(
        choices=[
            ('today', '📅 Сегодня'),
            ('week', '📅 За неделю'),
            ('month', '📅 За месяц'),
            ('year', '📅 За год'),
        ],
        method='filter_date_range',
        label='Период',
        empty_label='🕒 Всё время',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'style': 'max-width: 200px;'
        })
    )

    # ⭐ Фильтр по рейтингу
    rating = django_filters.ChoiceFilter(
        choices=[
            ('high', '⭐⭐⭐ Высокий (10+)'),
            ('medium', '⭐⭐ Средний (5-9)'),
            ('low', '⭐ Низкий (1-4)'),
            ('zero', '⚪ Нулевой'),
        ],
        method='filter_rating',
        label='⭐ Рейтинг',
        empty_label='⭐ Любой рейтинг',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'style': 'max-width: 220px;'
        })
    )

    # 📰 Фильтр по типу контента
    post_type = django_filters.ChoiceFilter(
        choices=Post.POST_TYPES,
        label='📰 Тип контента',
        empty_label='📰 Все типы',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'style': 'max-width: 200px;'
        })
    )

    # 🔄 Сортировка
    ordering = django_filters.OrderingFilter(
        choices=[
            ('-created_at', '🆕 Сначала новые'),
            ('created_at', '📅 Сначала старые'),
            ('-rating', '⭐ Высокий рейтинг'),
            ('rating', '⭐ Низкий рейтинг'),
            ('title', '🔤 А-Я'),
            ('-title', '🔤 Я-А'),
        ],
        label='🔄 Сортировка',
        empty_label='🔄 Без сортировки',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'style': 'max-width: 250px;'
        })
    )

    class Meta:
        model = Post
        fields = [
            'search', 'categories', 'author', 'date_range',
            'rating', 'post_type', 'ordering'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Динамически обновляем queryset для авторов (только те, у кого есть посты)
        self.filters['author'].queryset = Author.objects.filter(
            post__isnull=False
        ).select_related('user').distinct()

        # Динамически обновляем queryset для категорий (только с постами)
        self.filters['categories'].queryset = Category.objects.filter(
            post__isnull=False
        ).distinct()

    def filter_search(self, queryset, name, value):
        """Поиск по заголовку и содержанию"""
        if value:
            return queryset.filter(
                Q(title__icontains=value) |
                Q(content__icontains=value) |
                Q(author__user__username__icontains=value) |
                Q(categories__name__icontains=value)
            ).distinct()
        return queryset

    def filter_author(self, queryset, name, value):
        """Фильтр по автору"""
        if value:
            return queryset.filter(author=value)
        return queryset

    def filter_date_range(self, queryset, name, value):
        """Фильтр по диапазону дат"""
        now = timezone.now()

        if value == 'today':
            return queryset.filter(created_at__date=now.date())
        elif value == 'week':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=7))
        elif value == 'month':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=30))
        elif value == 'year':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=365))

        return queryset

    def filter_rating(self, queryset, name, value):
        """Фильтр по рейтингу"""
        if value == 'high':
            return queryset.filter(rating__gte=10)
        elif value == 'medium':
            return queryset.filter(rating__range=(5, 9))
        elif value == 'low':
            return queryset.filter(rating__range=(1, 4))
        elif value == 'zero':
            return queryset.filter(rating=0)

        return queryset


class ArticleFilter(PostFilter):
    """Специальный фильтр только для статей"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Скрываем фильтр по типу для статей
        self.filters.pop('post_type', None)

    class Meta:
        model = Post
        fields = ['search', 'categories', 'author', 'date_range', 'rating', 'ordering']


class NewsFilter(PostFilter):
    """Специальный фильтр только для новостей"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Скрываем фильтр по типу для новостей
        self.filters.pop('post_type', None)

    class Meta:
        model = Post
        fields = ['search', 'categories', 'author', 'date_range', 'rating', 'ordering']


# 🔄 Упрощенный фильтр для главной страницы
class QuickPostFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method='filter_search',
        label='Быстрый поиск',
        widget=forms.TextInput(attrs={
            'placeholder': 'Поиск по новостям...',
            'class': 'form-control form-control-sm'
        })
    )

    category = django_filters.ModelChoiceFilter(
        field_name='categories',
        queryset=Category.objects.all(),
        label='Категория',
        empty_label='Все категории',
        widget=forms.Select(attrs={
            'class': 'form-control form-control-sm'
        })
    )

    class Meta:
        model = Post
        fields = ['search', 'category']

    def filter_search(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(title__icontains=value) |
                Q(content__icontains=value)
            )
        return queryset

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Только категории с постами
        self.filters['category'].queryset = Category.objects.filter(
            post__isnull=False
        ).distinct()


# 🔄 Фильтр для страницы категории
class CategoryPostFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method='filter_search',
        label='Поиск в категории',
        widget=forms.TextInput(attrs={
            'placeholder': 'Поиск в этой категории...',
            'class': 'form-control'
        })
    )

    date_range = django_filters.ChoiceFilter(
        choices=[
            ('today', 'Сегодня'),
            ('week', 'За неделю'),
            ('month', 'За месяц'),
        ],
        method='filter_date_range',
        label='Период',
        empty_label='Все время',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    ordering = django_filters.OrderingFilter(
        choices=[
            ('-created_at', 'Сначала новые'),
            ('created_at', 'Сначала старые'),
            ('-rating', 'Высокий рейтинг'),
        ],
        label='Сортировка',
        empty_label='По умолчанию',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Post
        fields = ['search', 'date_range', 'ordering']

    def filter_search(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(title__icontains=value) |
                Q(content__icontains=value) |
                Q(author__user__username__icontains=value)
            )
        return queryset

    def filter_date_range(self, queryset, name, value):
        now = timezone.now()

        if value == 'today':
            return queryset.filter(created_at__date=now.date())
        elif value == 'week':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=7))
        elif value == 'month':
            return queryset.filter(created_at__gte=now - timezone.timedelta(days=30))

        return queryset