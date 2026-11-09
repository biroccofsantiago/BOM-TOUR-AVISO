import argparse
import json
import os
import smtplib
import ssl
import time
import unicodedata
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path


EVENT_URL = (
    "https://www.movistararena.com.ar/show/"
    "bdaa63bc-004b-463f-9df8-3bd00fee3e23"
)
CHECK_INTERVAL_SECONDS = 10 * 60
STATE_FILE = Path(__file__).with_name("availability_state.json")
DOTENV_FILE = Path(__file__).with_name(".env")
PURCHASE_BUTTON_SELECTOR = "button.btn-comprar"
SOLD_OUT_LABELS = {
    "agotad",
    "sin entradas",
    "no disponible",
    "proximamente",
    "sold out",
}


def load_dotenv(path=DOTENV_FILE):
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def mail_configuration():
    required = (
        "SMTP_HOST",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
    )
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise ValueError(
            "Falta configurar en .env: " + ", ".join(missing)
        )

    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError as exc:
        raise ValueError("SMTP_PORT debe ser un número.") from exc

    use_ssl = os.environ.get("SMTP_SSL", "false").strip().lower()
    if use_ssl not in {"true", "false"}:
        raise ValueError("SMTP_SSL debe ser true o false.")

    return {
        "host": os.environ["SMTP_HOST"],
        "port": port,
        "user": os.environ["SMTP_USER"],
        "password": os.environ["SMTP_PASSWORD"],
        "sender": os.environ["EMAIL_FROM"],
        "recipients": [
            address.strip()
            for address in os.environ["EMAIL_TO"].split(",")
            if address.strip()
        ],
        "use_ssl": use_ssl == "true",
    }


def check_availability():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "No está instalado Playwright. Ejecutá: "
            "pip install -r requirements.txt y playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=45000)
            buttons = page.locator(PURCHASE_BUTTON_SELECTOR)
            try:
                buttons.first.wait_for(state="attached", timeout=30000)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(
                    "No aparecieron los botones de compra; "
                    "no se puede confirmar el estado de las entradas."
                ) from exc

            return detect_availability(
                buttons.evaluate_all(
                    """elements => elements.map(element => ({
                        text: element.innerText.trim(),
                        enabled: !element.disabled
                    }))"""
                )
            )
        finally:
            browser.close()


def detect_availability(buttons):
    if not buttons:
        raise RuntimeError(
            "La página no mostró botones de compra; "
            "no se puede confirmar el estado de las entradas."
        )

    for button in buttons:
        label = unicodedata.normalize("NFKD", button["text"].lower())
        label = "".join(char for char in label if not unicodedata.combining(char))
        label = " ".join(label.split())
        is_unavailable = any(status in label for status in SOLD_OUT_LABELS)
        if button["enabled"] and label and not is_unavailable:
            return True
    return False


def read_previous_state():
    if not STATE_FILE.exists():
        return None

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer {STATE_FILE.name}: {exc}") from exc

    available = state.get("available")
    if not isinstance(available, bool):
        raise RuntimeError(f"{STATE_FILE.name} no contiene un estado válido.")
    return available


def save_state(available):
    state = {"available": available, "checked_at": datetime.now().isoformat()}
    try:
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RuntimeError(f"No se pudo guardar {STATE_FILE.name}: {exc}") from exc


def send_notification(config):
    message = EmailMessage()
    message["Subject"] = "¡Hay entradas disponibles en Movistar Arena!"
    message["From"] = config["sender"]
    message["To"] = ", ".join(config["recipients"])
    message.set_content(
        "El monitor detectó que al menos una fecha tiene habilitado el botón "
        "de compra para BOM: Lali + Miranda! / Miranda! + Lali.\n\n"
        f"Revisá el evento ahora: {EVENT_URL}\n\n"
        "La disponibilidad puede cambiar rápidamente."
    )

    context = ssl.create_default_context()
    if config["use_ssl"]:
        with smtplib.SMTP_SSL(
            config["host"], config["port"], timeout=30, context=context
        ) as server:
            server.login(config["user"], config["password"])
            server.send_message(message)
    else:
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(config["user"], config["password"])
            server.send_message(message)


def run_check(config):
    available = check_availability()
    previous = read_previous_state()
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    if available:
        print(f"[{now}] Hay al menos una fecha con entradas disponibles.")
        if previous is not True:
            send_notification(config)
            print(f"[{now}] Aviso enviado a {', '.join(config['recipients'])}.")
    else:
        print(f"[{now}] Todas las fechas aparecen agotadas.")

    if previous is not available:
        save_state(available)


def main():
    parser = argparse.ArgumentParser(
        description="Avisa por correo cuando se habiliten entradas para el show."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Hace una sola revisión y termina.",
    )
    args = parser.parse_args()

    load_dotenv()
    config = mail_configuration()

    while True:
        started = time.monotonic()
        try:
            run_check(config)
        except Exception as exc:
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            print(f"[{now}] Error durante la revisión: {exc}")
            if args.once:
                return 1

        if args.once:
            break
        time.sleep(max(0, CHECK_INTERVAL_SECONDS - (time.monotonic() - started)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
