import dataiku
from dataiku.customrecipe import *
import pandas as pd
import logging
# Import smtplib for the actual sending function
import smtplib
# Import the email modules we'll need
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import StringIO

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Get handles on datasets
output_A_names = get_output_names_for_role('output')
output = dataiku.Dataset(output_A_names[0]) if len(output_A_names) > 0 else None

people = dataiku.Dataset(get_input_names_for_role('contacts')[0])
attachments = [dataiku.Dataset(x) for x in get_input_names_for_role('attachments')]

# Read configuration
config = get_recipe_config()

recipient_column = config.get('recipient_column', None)
recipient_value = config.get('recipient_value', None)
sender_column = config.get('sender_column', None)
sender_value = config.get('sender_value', None)
subject_column = config.get('subject_column', None)
subject_value = config.get('subject_value', None)
body_column = config.get('body_column', None)
body_value = config.get('body_value', None)

smtp_host = config.get('smtp_host', None)
smtp_port = int(config.get('smtp_port', "25"))

attachment_type = config.get('attachment_type', "csv")


output_schema = list(people.read_schema())
output_schema.append({'name':'STATUS', 'type':'STRING'})
output_schema.append({'name':'mailsend_error', 'type':'STRING'})
output.write_schema(output_schema)

if not body_column and not body_value:
    raise Exception("NO body column nor body value specified")


# Prepare attachements
mime_parts = []

for a in attachments:

    if attachment_type == "excel":
        request_fmt = "excel"
    else:
        request_fmt = "tsv-excel-header"
        filename = a.full_name + ".csv"
        mimetype = ["text", "csv"]

    with a.raw_formatted_data(format=request_fmt) as stream:
        buf = stream.read()

    if attachment_type == "excel":
        app = MIMEApplication(buf, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        app.add_header("Content-Disposition", 'attachment', filename= a.full_name + ".xlsx")
        mime_parts.append(app)
    else:
        txt = MIMEText(buf, _subtype="csv", _charset="utf-8")
        txt.add_header("Content-Disposition", 'attachment', filename= a.full_name + ".csv")
        mime_parts.append(txt)


s = smtplib.SMTP(smtp_host, port=smtp_port)


def send_email(contact):
    if recipient_value:
        recipient = recipient_value
    elif recipient_column:
        recipient = contact[recipient_column]
    if body_value:
        email_text = body_value
    elif body_column:
        email_text = contact[body_column]
    if subject_value:
        email_subject = subject_value
    elif subject_column:
        email_subject = contact[subject_column]
    if sender_value:
        sender = sender_value
    elif sender_column:
        sender = contact[sender_column]

    msg = MIMEMultipart()

    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"]=  email_subject

    # Leave some space for proper displaying of the attachment
    msg.attach(MIMEText(email_text + "\n\n"))
    for a in mime_parts:
        msg.attach(a)

    s.sendmail(sender, [recipient], msg.as_string())

with output.get_writer() as writer:
    i = 0
    success=0
    fail = 0
    for contact in people.iter_rows():
        logging.info("Sending to %s" % contact)
        try:
            send_email(contact)
            d = dict(contact)
            d['STATUS'] = 'SUCCESS'
            success+=1
            if writer:
                writer.write_row_dict(d)
        except Exception as e:
            logging.exception("Send failed")
            fail+=1
            d = dict(contact)
            d['STATUS'] = 'FAILED'
            d['mailsend_error'] = str(e)
            if writer:
                writer.write_row_dict(d)

        i +=1
        if i % 5 == 0:
            logging.info("Sent %d mails (%d success %d fail)" % (i, success, fail))

s.quit()