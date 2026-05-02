import paypalrestsdk

paypalrestsdk.configure({
    "mode": "sandbox",
    "client_id": "AaPKLL6k-u_Y68Pa30kb-liwIuezx8fv89oj2OlxxAAK0iQ876f1PnAlIv1tJEL4KoqWHYXvrY0vmMBd",
    "client_secret": "EC96UJGizwRhbK5gNTcReQzYW6va6NoS-55zt1HHV2NjVI9OgLQrbsZnGc1QApvTyfgAprSUADn7lP3_"
})

def crear_pago(precio, nota):

    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": "https://discord.gg/wtdwAPyyWy",
            "cancel_url": "https://discord.gg/wtdwAPyyWy"
        },
        "transactions": [{
            "amount": {
                "total": str(precio),
                "currency": "EUR"
            },
            "description": "Compra Discord",
            "custom": nota
        }]
    })

    if payment.create():
        for link in payment.links:
            if link.rel == "approval_url":
                return link.href

    return None