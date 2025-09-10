from flask import Flask, request, render_template_string
import os
import stripe
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3

app = Flask(__name__)

# ------------------- Environment variables -------------------
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
STRIPE_SECRET = os.environ.get("STRIPE_SECRET")
STRIPE_PUBLIC = os.environ.get("STRIPE_PUBLIC")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
RENDER_URL = os.environ.get("RENDER_URL")  # e.g., https://invoice-app-eou7.onrender.com

stripe.api_key = STRIPE_SECRET

# ------------------- Database Setup -------------------
def init_db():
    conn = sqlite3.connect("invoices.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            amount INTEGER,
            paid INTEGER DEFAULT 0,
            session_id TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------- Homepage -------------------
@app.route("/", methods=["GET"])
def index():
    html = """
    <html>
      <body style="font-family: Arial; max-width: 500px; margin:auto; padding:20px;">
        <h2>Create Invoice</h2>
        <form action="/create_invoice" method="POST">
          <label>Email:</label><br>
          <input type="email" name="email" placeholder="Customer Email" required style="width:100%; padding:8px; margin-bottom:10px;"><br>
          <label>Amount (in cents):</label><br>
          <input type="number" name="amount" placeholder="5000 = $50.00" required style="width:100%; padding:8px; margin-bottom:10px;"><br>
          <button type="submit" style="padding:10px 20px; background:#4CAF50; color:white; border:none; border-radius:5px;">
            Send Invoice
          </button>
        </form>
        <p><a href="/invoices">View All Invoices</a></p>
      </body>
    </html>
    """
    return render_template_string(html)

# ------------------- Create Invoice -------------------
@app.route("/create_invoice", methods=["POST"])
def create_invoice():
    email = request.form.get("email")
    amount = int(request.form.get("amount"))

    # Create Stripe Checkout session
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Invoice for {email}"},
                "unit_amount": amount,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{RENDER_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{RENDER_URL}/cancel",
    )

    # Store invoice in database
    conn = sqlite3.connect("invoices.db")
    c = conn.cursor()
    c.execute("INSERT INTO invoices (email, amount, session_id) VALUES (?, ?, ?)", 
              (email, amount, session.id))
    conn.commit()
    conn.close()

    # Send email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Invoice"
    msg["From"] = EMAIL_USER
    msg["To"] = email
    html_content = f"""
    <html>
      <body>
        <p>Hello,</p>
        <p>You have an invoice of ${amount/100:.2f}.</p>
        <p>Click the button below to pay:</p>
        <a href="{session.url}" style="padding:10px 20px; background:#4CAF50; color:white; text-decoration:none; border-radius:5px;">
          Pay Invoice
        </a>
      </body>
    </html>
    """
    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, email, msg.as_string())
        server.quit()
    except Exception as e:
        print("Email sending failed:", e)

    # Confirmation page
    html = f"""
    <html>
      <body style="font-family: Arial; max-width: 500px; margin:auto; padding:20px;">
        <h2>Invoice Sent!</h2>
        <p>Invoice for ${amount/100:.2f} has been sent to {email}.</p>
        <a href="/" style="padding:10px 20px; background:#4CAF50; color:white; text-decoration:none; border-radius:5px;">
          Send Another Invoice
        </a>
        <p><a href="/invoices">View All Invoices</a></p>
      </body>
    </html>
    """
    return render_template_string(html)

# ------------------- Success / Cancel -------------------
@app.route("/success")
def success():
    return "<h2>Thank you! Your payment was successful.</h2>"

@app.route("/cancel")
def cancel():
    return "<h2>Payment canceled. You can try again.</h2>"

# ------------------- View All Invoices -------------------
@app.route("/invoices")
def invoices():
    conn = sqlite3.connect("invoices.db")
    c = conn.cursor()
    c.execute("SELECT id, email, amount, paid, session_id FROM invoices ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    html_rows = ""
    for invoice_id, email, amount, paid, session_id in rows:
        status = "Paid ✅" if paid else "Unpaid ❌"
        reminder_button = ""
        if not paid:
            reminder_button = f"""
            <form action="/send_reminder" method="POST" style="display:inline;">
                <input type="hidden" name="invoice_id" value="{invoice_id}">
                <button type="submit" style="padding:5px 10px; background:#FFA500; color:white; border:none; border-radius:3px;">
                    Send payment reminder
                </button>
            </form>
            """
        html_rows += f"<tr><td>{email}</td><td>${amount/100:.2f}</td><td>{status}</td><td>{reminder_button}</td></tr>"

    html = f"""
    <html>
      <body style="font-family: Arial; max-width: 800px; margin:auto; padding:20px;">
        <h2>All Invoices</h2>
        <table border="1" cellpadding="8" cellspacing="0">
          <tr><th>Email</th><th>Amount</th><th>Status</th><th>Action</th></tr>
          {html_rows}
        </table>
        <p><a href="/">Back to Create Invoice</a></p>
      </body>
    </html>
    """
    return render_template_string(html)

# ------------------- Send Payment Reminder -------------------
@app.route("/send_reminder", methods=["POST"])
def send_reminder():
    invoice_id = request.form.get("invoice_id")

    conn = sqlite3.connect("invoices.db")
    c = conn.cursor()
    c.execute("SELECT email, amount, session_id FROM invoices WHERE id=?", (invoice_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return "Invoice not found", 404

    email, amount, session_id = row
    session = stripe.checkout.Session.retrieve(session_id)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Payment Reminder"
    msg["From"] = EMAIL_USER
    msg["To"] = email
    html_content = f"""
    <html>
      <body>
        <p>Hello,</p>
        <p>This is a friendly reminder for your invoice of ${amount/100:.2f}.</p>
        <p>Click the button below to pay:</p>
        <a href="{session.url}" style="padding:10px 20px; background:#FFA500; color:white; text-decoration:none; border-radius:5px;">
          Send payment reminder
        </a>
      </body>
    </html>
    """
    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, email, msg.as_string())
        server.quit()
    except Exception as e:
        print("Email sending failed:", e)

    return f"Payment reminder sent to {email}. <a href='/invoices'>Back to invoices</a>"

# ------------------- Stripe Webhook -------------------
@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        conn = sqlite3.connect("invoices.db")
        c = conn.cursor()
        c.execute("UPDATE invoices SET paid=1 WHERE session_id=?", (session["id"],))
        conn.commit()
        conn.close()
        print(f"Payment successful for session ID: {session['id']}")

    return "", 200

# ------------------- Run App -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
