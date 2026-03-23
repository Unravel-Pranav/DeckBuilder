from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from hello.services.notifications import send_email, send_email_via
from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger

router = APIRouter()


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    logger.info("#health_check: Health Check Requested")
    return {"status": "ok"}


class SMTPOverride(BaseModel):
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    starttls: Optional[bool] = True
    from_email: Optional[str] = None


class EmailTestIn(BaseModel):
    to: List[EmailStr]
    subject: str = "SMTP test from CBRE Research Reports"
    message: str = "This is a test email to confirm SMTP configuration."
    smtp: Optional[SMTPOverride] = None


@router.post("/health/email-test", tags=["health"])
async def health_email_test(payload: EmailTestIn):
    try:
        logger.info(
            "#health_check: Email test - to=%s override=%s",
            payload.to,
            bool(payload.smtp),
        )
        configured = bool(
            settings.smtp_host and settings.smtp_port and settings.smtp_from_email
        )
        delivery_details = {}
        if payload.smtp:
            email_sent = await send_email_via(
                payload.to,
                payload.subject,
                payload.message,
                host=payload.smtp.host,
                port=payload.smtp.port,
                username=payload.smtp.username,
                password=payload.smtp.password,
                starttls=payload.smtp.starttls if payload.smtp.starttls is not None else True,
                from_email=payload.smtp.from_email or settings.smtp_from_email or "no-reply@example.com",
            )
            if not email_sent:
                logger.warning("#health_check: Email test failed - email was not sent")
                raise HTTPException(status_code=500, detail="Failed to send test email")
        else:
            delivery_details = await send_email(payload.to, payload.subject, payload.message)
            all_success = all(status == "Success" for status in delivery_details.values())
            if not all_success:
                failed_emails = [email for email, status in delivery_details.items() if status == "Failed"]
                logger.warning("#health_check: Email test failed for some recipients: %s", failed_emails)
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to send test email to: {', '.join(failed_emails)}"
                )
        
        logger.info("#health_check: Email test successful")
        return {
            "ok": True, 
            "configured": configured or bool(payload.smtp), 
            "email_sent": True,
            "delivery_details": delivery_details if delivery_details else None
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("#health_check: health_email_test failed", exc_info=err)
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {err}")
