# Aviso de entradas: Movistar Arena

Monitor para el show [BOM: Lali + Miranda! / Miranda! + Lali](https://www.movistararena.com.ar/show/bdaa63bc-004b-463f-9df8-3bd00fee3e23). GitHub Actions lo consulta cada 5 minutos aunque tu computadora esté apagada. Si detecta un botón de compra habilitado, envía un correo. No realiza compras.

## Configuración

1. En GitHub, abre **Settings → Secrets and variables → Actions** y crea estos repository secrets: `SMTP_HOST`, `SMTP_PORT`, `SMTP_SSL`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` y `EMAIL_TO`. El repositorio debe ser público para evitar cargos de Actions. No guardes contraseñas en archivos del repositorio.
2. En **Actions**, habilita workflows y ejecuta **Ticket availability monitor → Run workflow** para probar.

Ejemplo Gmail: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_SSL=false`; usa una contraseña de aplicación para `SMTP_PASSWORD`, no tu contraseña habitual.

El workflow apunta a revisar cada 5 minutos, pero GitHub puede demorar las tareas programadas: **no se garantiza un aviso en menos de 10 minutos**. La disponibilidad también puede agotarse antes de que llegue el correo.

El primer chequeo avisa si ya hay entradas. Luego solo vuelve a avisar cuando hayan pasado de agotadas a disponibles. Si el sitio no carga o no se pueden leer los botones, el chequeo falla explícitamente y no se toma como entradas liberadas.

## Prueba local opcional

Con Python 3.10+:

```powershell
py -m pip install -r requirements.txt
py -m playwright install chromium
Copy-Item .env.example .env
```

Completa `.env` con SMTP y ejecuta `py .\monitor.py --once`. Para revisar cada 10 minutos en una computadora encendida, ejecuta `py .\monitor.py`.

Pruebas: `py -m unittest .\test_monitor.py`.
