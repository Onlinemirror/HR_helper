"""
Запустите этот скрипт один раз для авторизации Google Drive.
Откроется браузер — войдите в свой Gmail-аккаунт и разрешите доступ.
Токен сохранится в drive_token.json и будет переиспользоваться ботом.

Запуск: python setup_drive_auth.py
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = os.getenv("OAUTH_CREDENTIALS_FILE", "oauth_credentials.json")
TOKEN_FILE = "credentials/drive_token.json"

def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Файл {CREDENTIALS_FILE!r} не найден.")
        print("Скачайте OAuth2 Client credentials из Google Cloud Console и положите в папку проекта.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"✅ Авторизация успешна! Токен сохранён в {TOKEN_FILE!r}")
    print("Теперь можно запускать бота: python bot.py")

if __name__ == "__main__":
    main()
