import os
from pathlib import Path
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-your-secret-key-here'
DEBUG = True
ALLOWED_HOSTS = []

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/news/'
LOGOUT_REDIRECT_URL = '/news/'

# 🆕 НАСТРОЙКИ КЭШИРОВАНИЯ
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': BASE_DIR / 'cache',  # Папка для кэша
        'TIMEOUT': 300,  # 5 минут по умолчанию
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.yandex',
    'django_filters',
    'django_celery_beat',
    'news',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'NewsPortal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['username*', 'email*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGOUT_REDIRECT_URL = '/news/'
ACCOUNT_SESSION_REMEMBER = True

ACCOUNT_FORMS = {
    'login': 'allauth.account.forms.LoginForm',
    'signup': 'allauth.account.forms.SignupForm',
    'reset_password': 'allauth.account.forms.ResetPasswordForm',
}

# 🆕 НАСТРОЙКИ EMAIL ДЛЯ СИСТЕМЫ ПОДПИСОК
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
SITE_URL = 'http://127.0.0.1:8000'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 🆕 Опционально: если хотите использовать медиа файлы
# MEDIA_URL = '/media/'
# MEDIA_ROOT = BASE_DIR / 'media'

# Настройки Celery
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # URL Redis брокера
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'  # Бэкенд для результатов
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Europe/Moscow'  # Установите вашу временную зону

# Настройки email (для разработки)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@newportal.com'

# Для периодических задач
CELERY_BEAT_SCHEDULE = {
    'send-weekly-digest-every-monday': {
        'task': 'news.tasks.send_weekly_digest_task',
        'schedule': 604800.0,  # Каждую неделю (в секундах)
        # 'schedule': crontab(hour=8, minute=0, day_of_week=1),  # Каждый понедельник в 8:00
    },
}

# 🆕 РАСШИРЕННЫЕ НАСТРОЙКИ ЛОГИРОВАНИЯ
# Создаем директорию для логов если её нет
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Настройки для email рассылки ошибок администраторам
ADMINS = [
    ('Администратор', 'admin@example.com'),
]

SERVER_EMAIL = 'server@newportal.com'
EMAIL_SUBJECT_PREFIX = '[News Portal] '

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        # Формат для DEBUG сообщений в консоль
        'verbose_console': {
            'format': '{asctime} - {levelname} - {message}',
            'style': '{',
        },
        # Формат для WARNING сообщений в консоль (с путем)
        'verbose_console_warning': {
            'format': '{asctime} - {levelname} - {pathname} - {message}',
            'style': '{',
        },
        # Формат для ERROR сообщений в консоль (с путем и стеком)
        'verbose_console_error': {
            'format': '{asctime} - {levelname} - {pathname} - {message}\n{exc_info}',
            'style': '{',
        },
        # Формат для general.log
        'general_file': {
            'format': '{asctime} - {levelname} - {module} - {message}',
            'style': '{',
        },
        # Формат для errors.log
        'error_file': {
            'format': '{asctime} - {levelname} - {message} - {pathname}\n{exc_info}',
            'style': '{',
        },
        # Формат для security.log
        'security_file': {
            'format': '{asctime} - {levelname} - {module} - {message}',
            'style': '{',
        },
        # Формат для email уведомлений
        'email': {
            'format': '{asctime} - {levelname} - {message} - {pathname}',
            'style': '{',
        },
    },

    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },

    'handlers': {
        # Консольные handlers для разных уровней (только при DEBUG=True)
        'console_debug': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose_console',
        },
        'console_warning': {
            'level': 'WARNING',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose_console_warning',
        },
        'console_error': {
            'level': 'ERROR',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose_console_error',
        },

        # Файловый handler для general.log (только при DEBUG=False)
        'file_general': {
            'level': 'INFO',
            'filters': ['require_debug_false'],
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'general.log',
            'formatter': 'general_file',
        },

        # Файловый handler для errors.log (всегда активен)
        'file_errors': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'errors.log',
            'formatter': 'error_file',
        },

        # Файловый handler для security.log (всегда активен)
        'file_security': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'security.log',
            'formatter': 'security_file',
        },

        # Email handler для администраторов (только при DEBUG=False)
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'formatter': 'email',
            'include_html': False,
        },
    },

    'loggers': {
        # Основной логгер Django - в консоль и general.log
        'django': {
            'handlers': ['console_debug', 'console_warning', 'console_error', 'file_general'],
            'level': 'DEBUG',
            'propagate': False,
        },

        # Логгеры для errors.log и email уведомлений
        'django.request': {
            'handlers': ['file_errors', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['file_errors', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.template': {
            'handlers': ['file_errors'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['file_errors'],
            'level': 'ERROR',
            'propagate': False,
        },

        # Логгер для security.log
        'django.security': {
            'handlers': ['file_security'],
            'level': 'DEBUG',
            'propagate': False,
        },

        # Кастомные логгеры для приложения news
        'news': {
            'handlers': ['console_debug', 'console_warning', 'console_error', 'file_general'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'news.views': {
            'handlers': ['console_debug', 'console_warning', 'console_error', 'file_general'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'news.admin': {
            'handlers': ['console_debug', 'console_warning', 'console_error', 'file_general'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'news.models': {
            'handlers': ['console_debug', 'console_warning', 'console_error', 'file_general'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'news.tasks': {
            'handlers': ['console_debug', 'console_warning', 'console_error', 'file_general'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },

    'root': {
        'handlers': ['console_debug', 'console_warning', 'console_error'],
        'level': 'DEBUG',
    },
}