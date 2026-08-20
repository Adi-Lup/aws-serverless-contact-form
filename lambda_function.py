import json
import os
import uuid
import boto3
from datetime import datetime, timezone
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("ses")

TABLE_NAME = os.environ["TABLE_NAME"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]

table = dynamodb.Table(TABLE_NAME)


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body)
    }


def lambda_handler(event, context):
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"message": "Request body is not valid JSON"})

    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip()
    message = str(payload.get("message", "")).strip()

    if not name or not email or not message:
        return response(400, {"message": "Fields name, email and message are required"})

    if "@" not in email or len(email) > 254:
        return response(400, {"message": "Email address is not valid"})

    if len(name) > 100 or len(message) > 2000:
        return response(400, {"message": "Name or message exceeds the allowed length"})

    submission_id = str(uuid.uuid4())
    submitted_at = datetime.now(timezone.utc).isoformat()

    item = {
        "submissionId": submission_id,
        "name": name,
        "email": email,
        "message": message,
        "submittedAt": submitted_at
    }

    try:
        table.put_item(Item=item)
    except ClientError as error:
        print(f"DynamoDB write failed: {error}")
        return response(500, {"message": "Could not save your message"})

    email_body = (
        f"New contact form submission\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Submitted at: {submitted_at}\n"
        f"Submission ID: {submission_id}\n\n"
        f"Message:\n{message}\n"
    )

    try:
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [RECIPIENT_EMAIL]},
            ReplyToAddresses=[email],
            Message={
                "Subject": {"Data": f"Kronos contact form: {name}"},
                "Body": {"Text": {"Data": email_body}}
            }
        )
    except ClientError as error:
        print(f"SES send failed: {error}")
        return response(202, {
            "message": "Message saved, but the notification email could not be sent",
            "submissionId": submission_id
        })

    return response(201, {
        "message": "Thank you, your message has been received",
        "submissionId": submission_id
    })
