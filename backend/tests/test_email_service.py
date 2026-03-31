from unittest.mock import patch, MagicMock
from app.services.email_service import send_otp_email


def test_send_otp_email_calls_resend():
    """send_otp_email 應呼叫 resend.Emails.send，帶正確的收件人和 OTP。"""
    mock_send = MagicMock()
    with patch("app.services.email_service.resend.Emails.send", mock_send):
        send_otp_email("user@example.com", "123456")

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == "user@example.com"
    assert "123456" in call_kwargs["text"]


def test_send_otp_email_raises_on_resend_error():
    """resend 拋出例外時，應 re-raise。"""
    with patch("app.services.email_service.resend.Emails.send", side_effect=Exception("API Error")):
        try:
            send_otp_email("user@example.com", "123456")
            assert False, "Should have raised"
        except Exception as e:
            assert "API Error" in str(e)
