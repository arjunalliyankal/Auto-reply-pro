import os.path
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from channels.base import BaseChannel

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = "data/token.json"


class GmailChannel(BaseChannel):
    """Gmail channel — reads unread emails and replies via Gmail API (OAuth2)."""

    def __init__(self, creds_path: str):
        """
        Initializes the Gmail service. 
        Handles OAuth2 flow using client secrets and persistent token storage.
        """
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        if os.path.exists(TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)

    def get_unread_messages(self) -> list[dict]:
        """Fetch all unread messages from the inbox."""
        try:
            results = self.service.users().messages().list(
                userId="me", q="is:unread"
            ).execute()
            messages = results.get("messages", [])
            full_msgs = []
            for m in messages:
                full = self.service.users().messages().get(
                    userId="me", id=m["id"], format="full"
                ).execute()
                full_msgs.append(full)
            return full_msgs
        except Exception as e:
            print(f"[Gmail] Error fetching messages: {e}")
            return []

    def get_messages(self) -> list[dict]:
        """Implements BaseChannel interface — wraps get_unread_messages."""
        return self.get_unread_messages()

    def extract_body(self, message: dict) -> str:
        """Extract plain text body from a full Gmail message."""
        parts = message.get("payload", {}).get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part["body"].get("data", "")
                return base64.urlsafe_b64decode(data).decode("utf-8")
        # Fallback: try top-level body
        body_data = message.get("payload", {}).get("body", {}).get("data", "")
        if body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8")
        return ""

    def get_header(self, message: dict, name: str) -> str:
        """Extract a header value by name from a Gmail message."""
        headers = message.get("payload", {}).get("headers", [])
        for h in headers:
            if h["name"].lower() == name.lower():
                return h["value"]
        return ""

    def send_reply(  # type: ignore[override]
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
    ) -> None:
        """Send a reply email in the original thread."""
        try:
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = f"Re: {subject}"
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            self.service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": thread_id},
            ).execute()
        except Exception as e:
            print(f"[Gmail] Error sending reply: {e}")

    def send_reply_with_images(
        self, to: str, subject: str, body: str, thread_id: str, images: list[dict]
    ) -> None:
        """Send a reply with any matched images as MIME attachments."""
        try:
            message = MIMEMultipart()
            message["to"]      = to
            message["subject"] = f"Re: {subject}"
            message.attach(MIMEText(body))

            for img in images:
                path = img["file_path"]
                ext = path.lower().split('.')[-1]
                with open(path, "rb") as f:
                    file_data = f.read()
                    if ext == "pdf":
                        mime_attachment = MIMEApplication(file_data, _subtype="pdf")
                    else:
                        mime_attachment = MIMEImage(file_data)
                        
                mime_attachment.add_header(
                    "Content-Disposition", "attachment",
                    filename=os.path.basename(path)
                )
                message.attach(mime_attachment)

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            self.service.users().messages().send(
                userId="me", body={"raw": raw, "threadId": thread_id}
            ).execute()
        except Exception as e:
            print(f"[Gmail] Error sending reply with images: {e}")

    def mark_as_read(self, message_id: str) -> None:
        """Mark a message as read by removing the UNREAD label."""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        except Exception as e:
            print(f"[Gmail] Error marking as read: {e}")
