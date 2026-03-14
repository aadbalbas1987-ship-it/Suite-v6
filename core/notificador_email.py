"""
core/notificador_email.py — RPA Suite v5.6
============================================
Notificación por email al terminar un lote de robot.

Usa SMTP con Gmail (o cualquier proveedor SMTP).
Configurar en .env:
  EMAIL_REMITENTE=tu@gmail.com
  EMAIL_PASSWORD=app_password_gmail
  EMAIL_DESTINATARIO=destino@gmail.com  (opcional, usa SSH_DEFAULT_EMAIL si no está)

Para Gmail: crear App Password en
  https://myaccount.google.com/apppasswords
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def _get_config() -> dict:
    return {
        "remitente":    os.getenv("EMAIL_REMITENTE", ""),
        "password":     os.getenv("EMAIL_PASSWORD", ""),
        "destinatario": os.getenv("EMAIL_DESTINATARIO", "") or os.getenv("SSH_DEFAULT_EMAIL", ""),
        "smtp_host":    os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        "smtp_port":    int(os.getenv("EMAIL_SMTP_PORT", "587")),
    }


def email_disponible() -> bool:
    """Retorna True si el email está configurado en .env."""
    cfg = _get_config()
    return bool(cfg["remitente"] and cfg["password"] and cfg["destinatario"])


def enviar_email(
    asunto: str,
    cuerpo_html: str,
    log_func=None,
) -> bool:
    """
    Envía un email con el asunto y cuerpo HTML indicados.
    Retorna True si el envío fue exitoso.
    """
    def _log(m):
        if log_func: log_func(m)

    cfg = _get_config()
    if not cfg["remitente"] or not cfg["password"]:
        _log("⚠ Email no configurado. Agregá EMAIL_REMITENTE y EMAIL_PASSWORD al .env.")
        return False
    if not cfg["destinatario"]:
        _log("⚠ Sin destinatario. Agregá EMAIL_DESTINATARIO al .env.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = cfg["remitente"]
        msg["To"]      = cfg["destinatario"]
        msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
            server.starttls()
            server.login(cfg["remitente"], cfg["password"])
            server.sendmail(cfg["remitente"], cfg["destinatario"], msg.as_string())

        _log(f"  ✅ Email enviado a {cfg['destinatario']}")
        return True
    except Exception as e:
        _log(f"  ❌ Error enviando email: {e}")
        return False


def notificar_lote_ok(
    robot: str,
    filas: int,
    archivo: str = "",
    duracion_seg: float = 0,
    dry_run: bool = False,
    log_func=None,
) -> bool:
    """Notifica por email que un lote terminó exitosamente."""
    if not email_disponible():
        return False

    modo = "🔵 DRY-RUN" if dry_run else "✅ PRODUCCIÓN"
    dur  = f"{duracion_seg:.0f}s" if duracion_seg else "—"
    hora = datetime.now().strftime("%d/%m/%Y %H:%M")

    asunto = f"✅ RPA Suite — {robot} completado ({filas} filas)"
    cuerpo = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1A1D23;">
    <div style="max-width:600px;margin:0 auto;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;">
      <div style="background:#1D3557;padding:20px 24px;">
        <h2 style="color:white;margin:0;">🤖 RPA Suite — Notificación</h2>
        <p style="color:#93C5FD;margin:4px 0 0;">{hora}</p>
      </div>
      <div style="padding:24px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr style="background:#EFF6FF;">
            <td style="padding:10px 14px;font-weight:bold;width:40%;">Robot</td>
            <td style="padding:10px 14px;">{robot}</td>
          </tr>
          <tr>
            <td style="padding:10px 14px;font-weight:bold;">Estado</td>
            <td style="padding:10px 14px;">{modo}</td>
          </tr>
          <tr style="background:#EFF6FF;">
            <td style="padding:10px 14px;font-weight:bold;">Filas procesadas</td>
            <td style="padding:10px 14px;">{filas}</td>
          </tr>
          <tr>
            <td style="padding:10px 14px;font-weight:bold;">Archivo</td>
            <td style="padding:10px 14px;">{archivo or '—'}</td>
          </tr>
          <tr style="background:#EFF6FF;">
            <td style="padding:10px 14px;font-weight:bold;">Duración</td>
            <td style="padding:10px 14px;">{dur}</td>
          </tr>
        </table>
        <p style="color:#16a34a;font-weight:bold;margin-top:16px;">
          ✅ El proceso finalizó correctamente.
        </p>
      </div>
      <div style="background:#F8FAFC;padding:12px 24px;border-top:1px solid #E2E8F0;">
        <small style="color:#94A3B8;">RPA Suite v5.6 — Andrés Díaz</small>
      </div>
    </div>
    </body></html>
    """
    return enviar_email(asunto, cuerpo, log_func)


def notificar_lote_error(
    robot: str,
    error: str,
    archivo: str = "",
    log_func=None,
) -> bool:
    """Notifica por email que un lote falló."""
    if not email_disponible():
        return False

    hora   = datetime.now().strftime("%d/%m/%Y %H:%M")
    asunto = f"❌ RPA Suite — Error en {robot}"
    cuerpo = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1A1D23;">
    <div style="max-width:600px;margin:0 auto;border:1px solid #FCA5A5;border-radius:12px;overflow:hidden;">
      <div style="background:#7F1D1D;padding:20px 24px;">
        <h2 style="color:white;margin:0;">❌ RPA Suite — Error</h2>
        <p style="color:#FCA5A5;margin:4px 0 0;">{hora}</p>
      </div>
      <div style="padding:24px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr style="background:#FEF2F2;">
            <td style="padding:10px 14px;font-weight:bold;width:40%;">Robot</td>
            <td style="padding:10px 14px;">{robot}</td>
          </tr>
          <tr>
            <td style="padding:10px 14px;font-weight:bold;">Archivo</td>
            <td style="padding:10px 14px;">{archivo or '—'}</td>
          </tr>
        </table>
        <div style="background:#FEF2F2;border-left:4px solid #EF4444;
                    padding:12px 16px;margin-top:16px;border-radius:0 8px 8px 0;">
          <strong>Error:</strong><br>
          <code style="font-size:12px;">{error}</code>
        </div>
        <p style="color:#DC2626;font-weight:bold;margin-top:16px;">
          ⚠ Revisá el log de la aplicación para más detalles.
        </p>
      </div>
      <div style="background:#FFF7F7;padding:12px 24px;border-top:1px solid #FCA5A5;">
        <small style="color:#94A3B8;">RPA Suite v5.6 — Andrés Díaz</small>
      </div>
    </div>
    </body></html>
    """
    return enviar_email(asunto, cuerpo, log_func)
