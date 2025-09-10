# app.py
import os
import smtplib
import sqlite3
import uuid
from flask import Flask, request, redirect, render_template, url_for
from email.mime.text import MIMEText
import stripe

app = Flask(__name__)

from flask import render_template_string

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
      </body>
    </html>
    """
    return render_template_string(html)

# === CONFIG ===
DATABASE = "invoices.db"
EMAIL_USER = os.getenv("EMAIL_USER")  # your Gmail
EMAIL_PASS = os.getenv("EMAIL_PASS")  # Gmail app password
STRIPE_SECRET = os.getenv("STRIPE_SECRET")  # Stripe secret key
STRIPE_PUBLIC = os.getenv("STRIPE_PUBLIC")  # Stripe publishable key

stripe.api_key = STRIPE_SECRET

# === DB INIT ===
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            customer_email TEXT,
            amount INTEGER,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# === ROUTES ===
@app.route("/")
def index():
    return "Invoice App Running!"

@app.route("/create_invoice", methods=["POST"])
def create_invoice():
    email = request.form["email"]
    amount = int(request.form["amount"])  # in cents
    invoice_id = str(uuid.uuid4())

    # Store invoice
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT INTO invoices VALUES (?, ?, ?, ?)",
              (invoice_id, email, amount, "unpaid"))
    conn.commit()
    conn.close()

    # Send email with pay link
    link = request.url_root + "pay/" + invoice_id
    msg = MIMEText(f"Hello! Please pay your invoice here: {link}")
    msg["Subject"] = "Your Invoice"
    msg["From"] = EMAIL_USER
    msg["To"] = email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

    return f"Invoice created and sent to {email}!"

@app.route("/pay/<invoice_id>")
def pay(invoice_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT amount, status FROM invoices WHERE id=?", (invoice_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return "Invoice not found", 404
    amount, status = row

    if status == "paid":
        return "Invoice already paid!"

    # Create Stripe Checkout session
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Invoice Payment"},
                "unit_amount": amount,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=request.url_root + f"success/{invoice_id}",
        cancel_url=request.url_root + f"pay/{invoice_id}",
    )
    return redirect(session.url, code=303)

@app.route("/success/<invoice_id>")
def success(invoice_id):
    # Mark invoice as paid
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE invoices SET status='paid' WHERE id=?", (invoice_id,))
    conn.commit()
    conn.close()
    return "Thank you! Your invoice has been paid."

# Webhook endpoint for Stripe
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig, endpoint_secret)
    except Exception as e:
        return str(e), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # Find invoice by success_url
        if "success/" in session["success_url"]:
            invoice_id = session["success_url"].split("success/")[-1]
            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute("UPDATE invoices SET status='paid' WHERE id=?", (invoice_id,))
            conn.commit()
            conn.close()
    return "ok", 200

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render gives us a port
    app.run(host="0.0.0.0", port=port, debug=True)




