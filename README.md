# Winter Desktop

Анимированный снег и сезонные эффекты на рабочем столе Windows и macOS.

**Автор:** Kendrr ([GitHub: @dororofofofor](https://github.com/dororofofofor))  
**Лицензия:** MIT — см. [LICENSE](LICENSE).

## Скачать готовое приложение

Готовые сборки появятся во вкладке **Releases** после запуска сборки GitHub Actions:

- **Windows 10/11:** `WinterDesktop.exe` — portable-программа, установка не требуется.
- **macOS Apple Silicon (M1/M2/M3/M4):** `WinterDesktop_macOS_arm64.zip` — архив с `Winter Desktop.app`.
- **macOS Intel:** `WinterDesktop_macOS_x86_64.zip` — архив с `Winter Desktop.app`.

## Как получить сборки

1. Загрузите содержимое репозитория на GitHub.
2. Откройте вкладку **Actions** и разрешите запуск GitHub Actions, если GitHub попросит.
3. Для тестовой сборки выберите **Build desktop apps** → **Run workflow**. Готовые файлы появятся внизу запуска в разделе **Artifacts**.
4. Чтобы создать публичный релиз с файлами во вкладке **Releases**, создайте тег версии:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

GitHub соберёт Windows `.exe` и macOS `.app` на соответствующих системах и приложит их к релизу. Сборки не хранятся в исходном репозитории — они создаются GitHub Actions.

## Запуск

- **Windows:** скачайте `WinterDesktop.exe` и запустите его.
- **macOS:** распакуйте ZIP, переместите `Winter Desktop.app` в «Программы». Так как приложение не подписано Developer ID и не нотарифицировано Apple, macOS может показать предупреждение. Для первого запуска используйте Finder → правый клик по приложению → **Открыть** → подтвердите запуск.

## Исходный код

- `winter.pyw` — версия для Windows.
- `winter_mac.py` — версия для macOS.

Сборки создаются из этих файлов автоматически. Для ручного запуска исходников потребуется Python и зависимости соответствующей платформы.
