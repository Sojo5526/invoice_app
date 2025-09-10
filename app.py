from flask import Flask, request, render_template_string
import os
import stripe
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# Environment variables
EMAIL_USER = os.environ.get("EMAIL_USER")      # Your Gmail
EMAIL_PASS = os.environ.get("EMAIL_PASS")      # Gmail App Password
STRIPE_SECRET = os.environ.get("STRIPE_SECRET")
STRIPE_PUBLIC = os.environ.get("STRIPE_PUBLIC")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
RENDER_URL = os.environ.get("RENDER_URL")      # Should be https://invoice-app-eou7.onrender.com

stripe.api_key = STRIPE_SECRET

# Homepage with invoice form
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

# Handle invoice creation
@app.route("/create_invoice", methods=["POST"])
def create_invoice():
    email = request.form.get("email")
    amount = int(request.form.get("amount"))

    # 1. Create Stripe Checkout session
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

    # 2. Send email with Pay link
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

    # 3. Confirmation page
    html = f"""
    <html>
      <body style="font-family: Arial; max-width: 500px; margin:auto; padding:20px;">
        <h2>Invoice Sent!</h2>
        <p>Invoice for ${amount/100:.2f} has been sent to {email}.</p>
        <a href="/" style="padding:10px 20px; background:#4CAF50; color:white; text-decoration:none; border-radius:5px;">
          Send Another Invoice
        </a>
      </body>
    </html>
    """
    return render_template_string(html)

# Success page after Stripe payment
@app.route("/success")
def success():
    return "<h2>Thank you! Your payment was successful.</h2>"

# Cancel page if payment fails
@app.route("/cancel")
def cancel():
    return "<h2>Payment canceled. You can try again.</h2>"

# Stripe webhook (optional)
@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    import stripe
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
        print(f"Payment successful for session ID: {session['id']}")

    return "", 200

# Run app on Render or locally
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

