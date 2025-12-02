from celery import shared_task
from news.services.email_service import EmailService
import logging

logger = logging.getLogger('news.tasks')


@shared_task
def send_weekly_digest_task():
    """Celery задача для отправки еженедельных дайджестов"""
    try:
        print("🚀 Запуск задачи Celery: отправка еженедельных дайджестов")
        result = EmailService.send_weekly_digest()
        logger.info(f"Еженедельные дайджесты отправлены: {result}")
        print(f"✅ Задача завершена: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка отправки еженедельных дайджестов: {e}")
        print(f"❌ Ошибка задачи: {e}")
        raise


@shared_task
def send_immediate_notification_task(post_id):
    """Celery задача для отправки мгновенных уведомлений"""
    try:
        from news.models import Post
        post = Post.objects.get(id=post_id)
        print(f"🚀 Запуск задачи Celery: уведомления для поста '{post.title}'")

        if post.post_type == Post.NEWS:
            EmailService.send_new_post_notification(post)
        else:
            EmailService.send_immediate_article_notification(post)

        print(f"✅ Уведомления отправлены для поста: {post.title}")
        return f"Уведомления отправлены для {post.title}"
    except Exception as e:
        logger.error(f"Ошибка отправки уведомлений: {e}")
        print(f"❌ Ошибка задачи: {e}")
        raise


@shared_task
def send_welcome_email_task(user_id, activation_url):
    """Celery задача для отправки приветственного письма"""
    try:
        from django.contrib.auth.models import User
        user = User.objects.get(id=user_id)
        print(f"🚀 Запуск задачи Celery: приветственное письмо для {user.email}")

        EmailService.send_welcome_email(user, activation_url)
        print(f"✅ Приветственное письмо отправлено: {user.email}")
        return f"Приветственное письмо отправлено {user.email}"
    except Exception as e:
        logger.error(f"Ошибка отправки приветственного письма: {e}")
        print(f"❌ Ошибка задачи: {e}")
        raise


@shared_task
def send_activation_success_task(user_id):
    """Celery задача для отправки письма об успешной активации"""
    try:
        from django.contrib.auth.models import User
        user = User.objects.get(id=user_id)
        print(f"🚀 Запуск задачи Celery: письмо активации для {user.email}")

        EmailService.send_activation_success_email(user)
        print(f"✅ Письмо активации отправлено: {user.email}")
        return f"Письмо активации отправлено {user.email}"
    except Exception as e:
        logger.error(f"Ошибка отправки письма активации: {e}")
        print(f"❌ Ошибка задачи: {e}")
        raise