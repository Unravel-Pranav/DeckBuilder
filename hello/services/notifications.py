from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable

from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_port and settings.smtp_from_email)


def _send_email_sync(
    to_emails: list[str], subject: str, text_body: str, html_body: str | None = None
) -> dict[str, str]:
    """Send email to multiple recipients and return status per recipient.
    
    Returns:
        Dict mapping email address to "Success" or "Failed"
    """
    results = {}
    host = settings.smtp_host
    port = int(settings.smtp_port or 0)
    username = settings.smtp_username
    password = settings.smtp_password
    use_starttls = settings.smtp_starttls

    if not host or not port:
        logger.warning(
            "[SMTP] Missing host/port; printing email instead for %d recipients",
            len(to_emails),
        )
        # In stub mode, mark all as success
        for email in to_emails:
            results[email] = "Success"
        return results

    # Send to each recipient individually to track per-recipient status
    for to_email in to_emails:
        try:
            msg = EmailMessage()
            msg["From"] = settings.smtp_from_email or "no-reply@example.com"
            msg["To"] = to_email
            msg["Subject"] = subject
            if html_body:
                msg.set_content(text_body)
                msg.add_alternative(html_body, subtype="html")
            else:
                msg.set_content(text_body)

            if use_starttls and port == 587:
                with smtplib.SMTP(host, port, timeout=20) as server:
                    server.ehlo()
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)
            else:
                # SSL (typical port 465) or plain
                if port == 465:
                    with smtplib.SMTP_SSL(
                        host, port, timeout=20, context=ssl.create_default_context()
                    ) as server:
                        if username and password:
                            server.login(username, password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(host, port, timeout=20) as server:
                        if username and password:
                            server.login(username, password)
                        server.send_message(msg)
            
            results[to_email] = "Success"
            logger.info("[SMTP] Successfully sent email to %s", to_email)
        except Exception as e:
            results[to_email] = "Failed"
            logger.error("[SMTP] Failed to send email to %s: %s", to_email, e)
    
    return results


async def send_email(
    to_emails: Iterable[str], subject: str, text_body: str, html_body: str | None = None
) -> dict[str, str]:
    """Send an email and return detailed status per recipient.
    
    Returns:
        Dict mapping email address to "Success" or "Failed"
        Returns empty dict if no recipients
    """
    recipients = list(to_emails)
    if not recipients:
        return {}
    if not _smtp_configured():
        # Dev fallback: print to console and mark as skipped (stub mode)
        logger.warning(
            "[SMTP] STUB MODE - would send to %s: %s\n%s",
            recipients,
            subject,
            text_body,
        )
        logger.warning("[SMTP] No actual email sent. Configure SMTP settings to enable email delivery.")
        # Return "Skipped" to indicate stub mode (not "Success" which is misleading)
        return {email: "Skipped" for email in recipients}
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, _send_email_sync, recipients, subject, text_body, html_body
        )
        return results
    except Exception as e:
        logger.error("[SMTP] Failed to send email: %s", e)
        # Mark all as failed on exception
        return {email: "Failed" for email in recipients}


async def send_report_notification(
    to_emails: list[str], 
    s3_path: str, 
    ppt_url: str | None = None, 
    trigger_source: str = "manual",
    report_name: str = "Your",
    schedule_name: str | None = None
) -> dict[str, str]:
    """Send a report notification email and return detailed status per recipient.
    
    Args:
        to_emails: List of recipient email addresses
        s3_path: S3 path to the report
        ppt_url: Optional presigned URL for the report
        trigger_source: "manual" (user-initiated) or "scheduled" (scheduler-initiated)
        report_name: Name of the report to include in the email body
        schedule_name: Name of the schedule (only for scheduled reports)
    
    Returns:
        Dict mapping email address to "Success" or "Failed"
    """
    logger.info(
        "send_report_notification: Sending notification - trigger_source=%s, recipients=%s, report_name=%s, schedule_name=%s",
        trigger_source, len(to_emails), report_name, schedule_name
    )
    
    # Use ppt_url if available, otherwise fallback to s3_path
    download_link = ppt_url if ppt_url else s3_path
    
    if trigger_source == "scheduled":
        subject = f"Your {report_name} report is ready"
        schedule_text = f" from schedule {schedule_name}" if schedule_name else ""
        text = f"Dear User,\n\nYour {report_name} report{schedule_text} has been generated and is ready for download.\n\n{download_link}\n\nThank you,\n\nCBRE Research Reports Generator"
        html = f"""
        <p>Dear User,</p>
        <p>Your {report_name} report{schedule_text} has been generated and is ready for download.</p>
        <p><a href="{download_link}">Click here to download your report</a></p>
        <p>Thank you,</p>
        <p>CBRE Research Reports Generator</p>
        """
    else:  # manual - user-initiated
        subject = f"Your {report_name} report is ready"
        text = f"Dear User,\n\nYour {report_name} report has been generated and is ready for download.\n\n{download_link}\n\nThank you,\n\nCBRE Research Reports Generator"
        html = f"""
        <p>Dear User,</p>
        <p>Your {report_name} report has been generated and is ready for download.</p>
        <p><a href="{download_link}">Click here to download your report</a></p>
        <p>Thank you,</p>
        <p>CBRE Research Reports Generator</p>
        """
    return await send_email(to_emails, subject, text, html)


async def send_report_failure_notification(
    to_emails: list[str],
    report_name: str,
    trigger_source: str = "manual"
) -> dict[str, str]:
    """Send a failure notification email when report generation completely fails.
    
    Args:
        to_emails: List of recipient email addresses
        report_name: Name of the report that failed
        trigger_source: "manual" (user-initiated) or "scheduled" (scheduler-initiated)
        
    Returns:
        Dict mapping email address to "Success" or "Failed"
    """
    logger.warning(
        "send_report_failure_notification: Sending failure notification - "
        "report=%s, trigger_source=%s, recipients=%s",
        report_name, trigger_source, len(to_emails)
    )
    
    if trigger_source == "scheduled":
        subject = "Scheduled Report Generation Issue"
    else:
        subject = "Report Generation Issue"
    
    # User-friendly, non-technical message
    text = f"""We encountered an issue while generating your report "{report_name}".

Please try again later or contact support if the problem persists.

Thanks,
CBRE Research Reports"""
    
    html = f"""
    <p>We encountered an issue while generating your report "<strong>{report_name}</strong>".</p>
    <p>Please try again later or contact support if the problem persists.</p>
    <p>Thanks,<br/>CBRE Research Reports</p>
    """
    
    return await send_email(to_emails, subject, text, html)


async def send_multi_market_report_notification(
    to_emails: list[str], 
    market_ppt_info: list[dict],  # List of {"market": str, "s3_path": str, "ppt_url": str, "status": "Success" or "Failed"}
    report_name: str,
    trigger_source: str = "manual"
) -> dict[str, str]:
    """Send a multi-market report notification email with all PPT links.
    
    Now supports showing both successful and failed markets in one email.
    
    Args:
        to_emails: List of recipient email addresses
        market_ppt_info: List of dicts with market, s3_path, ppt_url, and status for each market
        report_name: Name of the report
        trigger_source: "manual" (user-initiated) or "scheduled" (scheduler-initiated)
        
    Returns:
        Dict mapping email address to "Success" or "Failed"
    """
    # Separate successful and failed markets
    successful_markets = [info for info in market_ppt_info if info.get("status") == "Success"]
    failed_markets = [info for info in market_ppt_info if info.get("status") == "Failed"]
    
    logger.info(
        "send_multi_market_report_notification: Sending notification - report=%s, "
        "trigger_source=%s, markets=%s (success=%s, failed=%s), recipients=%s",
        report_name, trigger_source, len(market_ppt_info),
        len(successful_markets), len(failed_markets), len(to_emails)
    )
    
    # Determine email subject based on results
    if failed_markets:
        if trigger_source == "scheduled":
            subject = f"Scheduled multi-market report '{report_name}' is ready (some markets unavailable)"
        else:
            subject = f"Your multi-market report '{report_name}' is ready (some markets unavailable)"
    else:
        if trigger_source == "scheduled":
            subject = f"Scheduled multi-market report '{report_name}' is ready"
        else:
            subject = f"Your multi-market report '{report_name}' is ready"
    
    # Build text version
    text_lines = [f"Your report '{report_name}' has been generated with the following results:\n"]
    
    # Add successful markets
    if successful_markets:
        text_lines.append("Successful markets:")
        for info in successful_markets:
            market = info.get("market", "Unknown")
            ppt_url = info.get("ppt_url", "")
            s3_path = info.get("s3_path", "")
            download_link = ppt_url if ppt_url else s3_path
            text_lines.append(f"  ✓ {market}: {download_link}")
    
    # Add failed markets
    if failed_markets:
        text_lines.append("\nFailed markets:")
        for info in failed_markets:
            market = info.get("market", "Unknown")
            text_lines.append(f"  ✗ {market}: Generation failed")
    
    if failed_markets:
        text_lines.append("\nSome markets could not be generated. Please contact support if you need assistance.")
    
    text_lines.append("\nThanks,\nCBRE Research Reports")
    text = "\n".join(text_lines)
    
    # Build HTML version with styled buttons
    html_lines = [
        f"<p>Your report '<strong>{report_name}</strong>' has been generated with the following results:</p>",
        "<table style='width: 100%; max-width: 600px; border-collapse: collapse; margin: 20px 0;'>"
    ]
    
    # Add successful markets with download links
    for info in successful_markets:
        market = info.get("market", "Unknown")
        ppt_url = info.get("ppt_url", "")
        s3_path = info.get("s3_path", "")
        download_link = ppt_url if ppt_url else s3_path
        
        html_lines.append(f"""
        <tr style='border-bottom: 1px solid #e0e0e0;'>
            <td style='padding: 15px 10px; width: 40%;'><span style='color: #00A758; font-weight: bold;'>✓</span> {market}</td>
            <td style='padding: 15px 10px;'>
                <a href="{download_link}">Download</a>
            </td>
        </tr>
        """)
    
    # Add failed markets with error indication
    for info in failed_markets:
        market = info.get("market", "Unknown")
        html_lines.append(f"""
        <tr style='border-bottom: 1px solid #e0e0e0;'>
            <td style='padding: 15px 10px; width: 40%;'><span style='color: #D32F2F; font-weight: bold;'>✗</span> {market}</td>
            <td style='padding: 15px 10px; text-align: center; color: #666;'>
                Generation failed
            </td>
        </tr>
        """)
    
    html_lines.append("</table>")
    
    if failed_markets:
        html_lines.append("<p style='color: #D32F2F;'>Some markets could not be generated. Please contact support if you need assistance.</p>")
    
    html_lines.append("<p>Thanks,<br/>CBRE Research Reports</p>")
    html = "\n".join(html_lines)
    
    return await send_email(to_emails, subject, text, html)


def _send_email_with_attachment_sync(
    to_emails: list[str],
    subject: str,
    text_body: str,
    html_body: str | None,
    attachment_bytes: bytes,
    attachment_filename: str = "report.pptx",
    content_type: str = "application/vnd.openxmlformats-officedocument.presentationml.presentation",
) -> None:
    """Construct an email with attachment and send via SMTP."""
    msg = EmailMessage()
    msg["From"] = settings.smtp_from_email or "no-reply@example.com"
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    if html_body:
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
    else:
        msg.set_content(text_body)

    # Attach PPTX (or provided content_type)
    try:
        maintype, subtype = (content_type.split("/", 1) + ["octet-stream"])[:2]
    except Exception:
        maintype, subtype = "application", "octet-stream"
    msg.add_attachment(
        attachment_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=attachment_filename,
    )

    host = settings.smtp_host
    port = int(settings.smtp_port or 0)
    username = settings.smtp_username
    password = settings.smtp_password
    use_starttls = settings.smtp_starttls

    if not host or not port:
        raise RuntimeError("SMTP host/port not configured for attachments")

    if use_starttls and int(port) == 587:
        with smtplib.SMTP(host, int(port), timeout=20) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(msg)
    elif int(port) == 465:
        with smtplib.SMTP_SSL(
            host, int(port), timeout=20, context=ssl.create_default_context()
        ) as server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, int(port), timeout=20) as server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)


async def send_email_with_attachment(
    to_emails: Iterable[str],
    subject: str,
    text_body: str,
    html_body: str | None,
    *,
    attachment_bytes: bytes,
    attachment_filename: str = "report.pptx",
    content_type: str = "application/vnd.openxmlformats-officedocument.presentationml.presentation",
) -> bool:
    """Send an email with attachment and return True if successful, False otherwise."""
    recipients = list(to_emails)
    if not recipients:
        return False
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _send_email_with_attachment_sync,
            recipients,
            subject,
            text_body,
            html_body,
            attachment_bytes,
            attachment_filename,
            content_type,
        )
        return True
    except Exception as e:
        logger.error("[SMTP] Failed to send email with attachment: %s", e)
        return False


async def send_email_via(
    to_emails: Iterable[str],
    subject: str,
    text_body: str,
    html_body: str | None = None,
    *,
    host: str,
    port: int,
    username: str | None = None,
    password: str | None = None,
    starttls: bool = True,
    from_email: str | None = None,
) -> bool:
    """Send email using explicit SMTP server details (override environment).

    Useful for testing with a provided "test SMTP" snippet without modifying .env.
    Returns True if successful, False otherwise.
    """
    recipients = list(to_emails)
    if not recipients:
        return False

    def _send_override():
        msg = EmailMessage()
        msg["From"] = from_email or settings.smtp_from_email or "no-reply@example.com"
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        if html_body:
            msg.set_content(text_body)
            msg.add_alternative(html_body, subtype="html")
        else:
            msg.set_content(text_body)

        if starttls and port == 587:
            with smtplib.SMTP(host, int(port), timeout=20) as server:
                server.ehlo(); server.starttls(context=ssl.create_default_context()); server.ehlo()
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        else:
            if int(port) == 465:
                with smtplib.SMTP_SSL(host, int(port), timeout=20, context=ssl.create_default_context()) as server:
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, int(port), timeout=20) as server:
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_override)
        return True
    except Exception as e:
        logger.error("[SMTP] Failed to send email via custom SMTP: %s", e)
        return False
