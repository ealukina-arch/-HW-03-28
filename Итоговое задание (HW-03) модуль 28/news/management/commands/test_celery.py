from django.core.management.base import BaseCommand
from news.tasks import send_weekly_digest_task


class Command(BaseCommand):
    help = 'Тестирование Celery задач'

    def handle(self, *args, **options):
        self.stdout.write("🧪 Тестирование Celery...")

        # Запуск задачи асинхронно
        result = send_weekly_digest_task.delay()

        self.stdout.write(
            self.style.SUCCESS(f"✅ Задача отправлена! ID задачи: {result.id}")
        )
        self.stdout.write(
            self.style.WARNING("📝 Проверьте консоль Celery worker для просмотра выполнения задачи")
        )