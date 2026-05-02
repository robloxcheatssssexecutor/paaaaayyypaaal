# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio, json, os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from discord import app_commands
import random
from datetime import timedelta
from flask import Flask, request
import threading
from paypal import crear_pago

TOKEN = "MTQ2NzkwNTk2ODQ4NTQzNzYwNQ.GenMM3.CWNuW_Lh_-2c5vI92mL1tNGEWHmlgGKp0Ih2Pk"
LOG_CHANNEL_ID = 1489949674369716286
VOUCH_CHANNEL_ID = 1430650990595412048
GUILD_ID = 1459852111108898848
PAYMENT_COOLDOWN = {}
INVITES_FILE = "invites.json"
PRODUCTS_FILE = "productos.json"
CONFIG_FILE = "config.json"

GUILD_INVITES = {}

# ---------------------------
# Sistema de invitaciones
# ---------------------------
def load_invites():
    if not os.path.exists(INVITES_FILE):
        return {}
    with open(INVITES_FILE, "r") as f:
        return json.load(f)

def save_invites(data):
    with open(INVITES_FILE, "w") as f:
        json.dump(data, f, indent=2)

INVITES = load_invites()

# ---------------------------
# Configuración paypal
# ---------------------------
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"paypal_email": "eqsh66@hotmail.com"}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

CONFIG = load_config()

# ---------------------------
# Productos
# ---------------------------
def load_products():
    default = {"1": [], "2": [], "3": []}

    if not os.path.exists(PRODUCTS_FILE):
        return default

    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # asegurar claves
    for key in default:
        if key not in data:
            data[key] = []

    return data

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

PRODUCTS = load_products()
PAGOS_FILE = "pagos.json"

def load_pagos():
    if not os.path.exists(PAGOS_FILE):
        return {}
    with open(PAGOS_FILE, "r") as f:
        return json.load(f)

def save_pagos(data):
    with open(PAGOS_FILE, "w") as f:
        json.dump(data, f, indent=2)

PAGOS = load_pagos()

def guardar_pago(nota, user_id, product, price, link, channel_id):
    PAGOS[nota] = {
        "user_id": user_id,
        "product": product,
        "price": price,
        "link": link,
        "channel_id": channel_id,
        "pagado": False
    }
    save_pagos(PAGOS)

PAGE_NAMES = {
    "1": "Fivem Shop",
    "2": "PC Optimizer",
    "3": "Others"
}

# ---------------------------
# Config bot
# ---------------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

tree = bot.tree

# ---------------------------
# Correo Gmail
# ---------------------------
def enviar_correo(user, metodo):
    remitente = "angelartizoffi@gmail.com"
    destinatario = "cludyshop@gmail.com"
    contraseña = "lytgrtoehjstlper"

    asunto = "Nuevo pago confirmado"
    cuerpo = f"{user} ha pagado con {metodo}"

    msg = MIMEMultipart()
    msg["From"] = remitente
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(remitente, contraseña)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")

# ---------------------------
# Select / TicketView (fix 50035)
# ---------------------------
class ProductSelect(discord.ui.Select):
    def __init__(self, products, page_id="1"):
        options = []

        for index, (name, price, link) in enumerate(products):
            unique_value = f"{page_id}:{index}|{name}|{price}|{link}"
            options.append(
                discord.SelectOption(
                    label=f"💎 {name}",
                    description=f"Price: {price}€",
                    value=unique_value
                )
            )

        super().__init__(
            placeholder=f"Select a product ({PAGE_NAMES[page_id]})",
            options=options,
            custom_id=f"product_select_{page_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        raw = self.values[0]
        page_id, rest = raw.split(":", 1)
        index, name, price, link = rest.split("|")
        await create_ticket(interaction, name, price, link)

class BuyAgainButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Comprar otro producto (manual)",
            style=discord.ButtonStyle.success,
            emoji="🛒",
            custom_id="buy_again_button"
        )

    async def callback(self, interaction: discord.Interaction):
        await create_ticket(interaction)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        for page_id, products in PRODUCTS.items():
            if products:
                self.add_item(ProductSelect(products, page_id))

        # 🔥 BOTÓN NUEVO
        self.add_item(BuyAgainButton())

class MainTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🛠 Soporte",
        style=discord.ButtonStyle.primary,
        custom_id="main_ticket_soporte"
    )
    async def soporte(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_simple_ticket(interaction, "soporte")

    @discord.ui.button(
        label="🛒 Comprar",
        style=discord.ButtonStyle.success,
        custom_id="main_ticket_comprar"
    )
    async def comprar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Selecciona un producto:",
            view=BuyMenuView(),
            ephemeral=True
        )

class BuyMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        for page_id, products in PRODUCTS.items():
            if products:
                self.add_item(ProductSelect(products, page_id))

        self.add_item(ManualPurchaseButton())


class ManualPurchaseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Compra manual",
            style=discord.ButtonStyle.secondary,
            emoji="✍️"
        )

    async def callback(self, interaction: discord.Interaction):
        await create_ticket(interaction)

async def create_simple_ticket(interaction, tipo):
    guild = interaction.guild
    user = interaction.user

    category = discord.utils.get(guild.categories, name="Auto bot tickets")
    if category is None:
        await interaction.response.send_message(
            "❌ No existe la categoría.",
            ephemeral=True
        )
        return

    channel = await guild.create_text_channel(
        f"{tipo}-{user.name}",
        category=category
    )

    await channel.set_permissions(guild.default_role, read_messages=False)
    await channel.set_permissions(user, read_messages=True)

    embed = discord.Embed(
        title=f"🎟 Ticket de {tipo.capitalize()}",
        description="Un miembro del equipo te atenderá pronto.",
        color=discord.Color.blue()
    )

    await channel.send(user.mention, embed=embed)
    await interaction.response.send_message(
        f"✅ Ticket de {tipo} creado: {channel.mention}",
        ephemeral=True
    )

# ---------------------------
# Crear ticket
# ---------------------------
async def create_ticket(interaction, product=None, price=None, link=None):

    guild = interaction.guild
    user = interaction.user
    ADMIN_ID = 1413847086767673474

    category = discord.utils.get(guild.categories, name="Auto bot tickets")
    if category is None:
        await interaction.response.send_message("❌ No existe la categoría.", ephemeral=True)
        return

    channel = await guild.create_text_channel(
        f"ticket-{user.id}",
        category=category
    )
    await channel.set_permissions(guild.default_role, read_messages=False)
    await channel.set_permissions(user, read_messages=True)

    # ---------------------------
    # VISTA MÉTODOS DE PAGO
    # ---------------------------
    class PaymentMethodView(View):
        def __init__(self):
            super().__init__(timeout=None)

        async def interaction_check(self, interaction):
            return interaction.user == user

        @discord.ui.button(label="Litecoin", style=discord.ButtonStyle.primary)
        async def ltc(self, interaction, button):

            amount_text = f"{price}€" if price else "el importe acordado"

            mensaje = f"""Envia {amount_text} a esta direccion de litecoin:
        ```LRYC9MwKQDzPRqdh4MpAy3pv4MQRzNGGEG```

        Pulsa abajo cuando pagues y espera a <@{ADMIN_ID}>"""

            await interaction.response.edit_message(
                content=mensaje,
                view=PaymentConfirmView("Litecoin")
            )

        @discord.ui.button(label="PayPal", style=discord.ButtonStyle.success)
        async def paypal(self, interaction, button):

            nota = f"ORDER-{random.randint(10000,99999)}"

            link = crear_pago(price, nota)

            guardar_pago(
                nota,
                interaction.user.id,
                product,
                price,
                link,
                interaction.channel.id
            )

            if not link:
                await interaction.response.send_message(
                    "❌ Error creando el pago.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="💳 Pago PayPal automático",
                description="Haz clic abajo para pagar de forma segura",
                color=discord.Color.green()
            )

            embed.add_field(
                name="💰 Precio",
                value=f"{price}€",
                inline=False
            )

            embed.add_field(
                name="🧾 ID Pedido",
                value=nota,
                inline=False
            )

            embed.add_field(
                name="🔗 Pago",
                value=f"[PAGAR AHORA]({link})",
                inline=False
            )

            await interaction.response.edit_message(
                embed=embed,
                view=PaymentConfirmView("PayPal", nota)
            )

        @discord.ui.button(label="Stripe (Tarjeta)", style=discord.ButtonStyle.secondary)
        async def stripe(self, interaction, button):
            await interaction.response.edit_message(
                content=f"Compra aquí: https://cludyyshopp.mysellauth.com/\nSi no está tu producto espera a <@{ADMIN_ID}>",
                view=PaymentConfirmView("Stripe")
            )

        @discord.ui.button(label="Bizum", style=discord.ButtonStyle.primary)
        async def bizum(self, interaction, button):
            await interaction.response.edit_message(
                content=f"Perfecto, espera a <@{ADMIN_ID}>",
                view=PaymentConfirmView("Bizum")
            )

        @discord.ui.button(label="Otra Crypto", style=discord.ButtonStyle.primary)
        async def crypto(self, interaction, button):
            await interaction.response.edit_message(
                content=f"Perfecto, espera a <@{ADMIN_ID}>",
                view=PaymentConfirmView("Crypto")
            )

    # ---------------------------
    # VISTA CONFIRMACIÓN
    # ---------------------------
    class PaymentConfirmView(View):
        def __init__(self, method, nota=None):
            super().__init__(timeout=None)
            self.method = method
            self.nota = nota

        async def interaction_check(self, interaction):
            return interaction.user == user

        @discord.ui.button(label="Ya he pagado", style=discord.ButtonStyle.success)
        async def paid(self, interaction, button):

            user_id = interaction.user.id
            now = asyncio.get_event_loop().time()

            # ⛔ COOLDOWN (120s = 2 min)
            if user_id in PAYMENT_COOLDOWN:
                if now - PAYMENT_COOLDOWN[user_id] < 120:
                    await interaction.response.send_message(
                        "⛔ Espera antes de volver a pulsar este botón.",
                        ephemeral=True
                    )
                    return

            PAYMENT_COOLDOWN[user_id] = now

            # 📧 enviar correo
            enviar_correo(interaction.user, self.method)

            # 🔄 renombrar canal
            try:
                await interaction.channel.edit(name=f"pagado-{self.method.lower()}")
            except:
                pass

            # 💬 mensaje
            resumen = (
                f"🧾 **Resumen de compra**\n"
                f"👤 Cliente: {interaction.user.mention}\n"
                f"🛒 Producto: **{product or 'Compra manual'}**\n"
                f"💰 Precio: **{price + '€' if price else 'Importe acordado'}**\n"
                f"💳 Método de pago: **{self.method}**"
                f"🧾 Nota: {self.nota or 'N/A'}\n"
            )

            await interaction.channel.send(resumen)

            await interaction.response.send_message(
                "✅ Pago notificado correctamente.",
                ephemeral=True
            )

        @discord.ui.button(label="Elegir otro método", style=discord.ButtonStyle.secondary)
        async def change(self, interaction, button):
            await interaction.response.edit_message(
                content="¿Qué método de pago usarás?",
                view=PaymentMethodView()
            )

        @discord.ui.button(label="📦 Entregar producto", style=discord.ButtonStyle.danger)
        async def deliver(self, interaction, button):
            admin_role = discord.utils.get(interaction.guild.roles, name="Administrador")
            if admin_role not in interaction.user.roles:
                await interaction.response.send_message("❌ Admin only.", ephemeral=True)
                return

            await interaction.channel.send(f"📦 Producto:\n{link}")
            await interaction.response.send_message("✅ Entregado.", ephemeral=True)

    # ---------------------------
    # MENSAJE INICIAL
    # ---------------------------
    descripcion = "¿Qué método de pago usarás?"

    # Si el ticket proviene de una compra, mostrar datos del producto
    if product and price:
        descripcion = (
            f"🛒 **Producto:** {product}\n"
            f"💰 **Precio:** {price}€\n\n"
            "Selecciona el método de pago."
        )

    embed = discord.Embed(
        title="💳 Método de pago",
        description=descripcion,
        color=discord.Color.blue()
    )

    await channel.send(embed=embed, view=PaymentMethodView())
    await interaction.response.send_message("❤️ Ticket creado.", ephemeral=True)

    log = guild.get_channel(LOG_CHANNEL_ID)
    if log:
        await log.send(f"📥 Ticket creado por {user.mention} para **{product}** en {channel.mention}")

# ============ verificacion para evitar falos si el bot se reinicia ======================
@bot.event
async def on_member_join(member):
    guild = member.guild

    try:
        new_invites = await guild.invites()
        old_invites = GUILD_INVITES.get(guild.id, [])

        used_invite = None

        for invite in new_invites:
            for old in old_invites:
                if invite.code == old.code and invite.uses > old.uses:
                    used_invite = invite
                    break

        if used_invite and used_invite.inviter:
            user_id = str(used_invite.inviter.id)
            INVITES[user_id] = INVITES.get(user_id, 0) + 1
            save_invites(INVITES)

        GUILD_INVITES[guild.id] = new_invites

    except Exception as e:
        print("Error invites:", e)

# ---------------------------
# LOG DE ERRORES AL CANAL
# ---------------------------
@bot.event
async def on_command_error(ctx, error):
    log = ctx.guild.get_channel(LOG_CHANNEL_ID)
    if log:
        await log.send(f"❌ Error en comando `{ctx.command}`:\n```\n{error}\n```")
    raise error

# ---------------------------
# Cambiar PayPal
# ---------------------------
@bot.command()
async def newpaypal(ctx, new_mail: str):
    admin_role = discord.utils.get(ctx.guild.roles, name="Administrador")
    if admin_role not in ctx.author.roles:
        await ctx.send("❌ No permiso.")
        return

    if "@" not in new_mail:
        await ctx.send("❌ Email inválido.")
        return

    CONFIG["paypal_email"] = new_mail
    save_config(CONFIG)
    await ctx.send(f"✅ PayPal actualizado a **{new_mail}**")

# ---------------------------
# Productos
# ---------------------------
@bot.command()
async def productos(ctx):
    admin_role = discord.utils.get(ctx.guild.roles, name="Administrador")
    if admin_role not in ctx.author.roles:
        await ctx.send("❌ No permiso.")
        return

    for page_id, products in PRODUCTS.items():
        if not products:
            continue
        embed = discord.Embed(
            title=f"📦 {PAGE_NAMES[page_id]}",
            color=discord.Color.green()
        )
        for name, price, link in products:
            embed.add_field(name=f"💎 {name}", value=f"{price}€", inline=False)

        await ctx.author.send(embed=embed)

    await ctx.send("📬 Productos enviados por DM.")

@bot.command()
async def addproducto(ctx, *, args: str):
    admin_role = discord.utils.get(ctx.guild.roles, name="Administrador")
    if admin_role not in ctx.author.roles:
        await ctx.send("❌ No permiso.")
        return

    try:
        name, price, page, link = args.rsplit(" ", 3)
    except:
        await ctx.send("❌ Uso: !addproducto <nombre> <precio> <pagina> <link>")
        return

    if page not in ["1", "2", "3"]:
        await ctx.send("❌ Página 1/2/3.")
        return

    PRODUCTS[page].append((name, price, link))
    save_products(PRODUCTS)

    await ctx.send(f"✅ Producto añadido: **{name}**")

@bot.command()
async def delproducto(ctx, *, name: str):
    admin_role = discord.utils.get(ctx.guild.roles, name="Administrador")
    if admin_role not in ctx.author.roles:
        await ctx.send("❌ No permiso.")
        return

    found = False
    for page in ["1", "2", "3"]:
        new_list = [p for p in PRODUCTS[page] if p[0].lower() != name.lower()]
        if len(new_list) != len(PRODUCTS[page]):
            PRODUCTS[page] = new_list
            found = True

    if not found:
        await ctx.send("❌ Producto no encontrado.")
        return

    save_products(PRODUCTS)
    await ctx.send(f"🗑️ Eliminado: **{name}**")

class AddProductModal(discord.ui.Modal, title="Añadir producto"):
    nombre = discord.ui.TextInput(label="Nombre")
    precio = discord.ui.TextInput(label="Precio")
    pagina = discord.ui.TextInput(label="Página (1/2/3)")
    link = discord.ui.TextInput(label="Link")

    async def on_submit(self, interaction: discord.Interaction):
        page = self.pagina.value.strip()

        if page not in ["1", "2", "3"]:
            await interaction.response.send_message("❌ Página inválida (1,2,3)", ephemeral=True)
            return

        PRODUCTS[page].append(
            (self.nombre.value, self.precio.value, self.link.value)
        )

        save_products(PRODUCTS)
        await interaction.response.send_message("✅ Producto añadido", ephemeral=True)

class EditProductModal(discord.ui.Modal, title="Editar producto"):
    nombre = discord.ui.TextInput(label="Nombre actual (obligatorio)")

    nuevo_nombre = discord.ui.TextInput(label="Nuevo nombre", required=False)
    nuevo_precio = discord.ui.TextInput(label="Nuevo precio", required=False)
    nuevo_link = discord.ui.TextInput(label="Nuevo link", required=False)
    nueva_pagina = discord.ui.TextInput(label="Nueva página (1/2/3)", required=False)

    async def on_submit(self, interaction: discord.Interaction):

        encontrado = False

        for page in PRODUCTS:
            for i, p in enumerate(PRODUCTS[page]):
                if p[0] == self.nombre.value:

                    name = self.nuevo_nombre.value or p[0]
                    price = self.nuevo_precio.value or p[1]
                    link = self.nuevo_link.value or p[2]
                    new_page = self.nueva_pagina.value.strip() if self.nueva_pagina.value else page

                    if new_page not in ["1", "2", "3"]:
                        await interaction.response.send_message("❌ Página inválida", ephemeral=True)
                        return

                    # eliminar antiguo
                    PRODUCTS[page].pop(i)

                    # añadir nuevo
                    PRODUCTS[new_page].append((name, price, link))

                    encontrado = True
                    break

        if not encontrado:
            await interaction.response.send_message("❌ Producto no encontrado", ephemeral=True)
            return

        save_products(PRODUCTS)
        await interaction.response.send_message("✏️ Producto actualizado", ephemeral=True)

class ProductSelectDelete(discord.ui.Select):
    def __init__(self):
        options = []

        for page, items in PRODUCTS.items():
            for i, (name, price, link) in enumerate(items):
                options.append(
                    discord.SelectOption(
                        label=name,
                        description=f"{price}€ ({PAGE_NAMES[page]})",
                        value=f"{page}|{i}"
                    )
                )

        super().__init__(
            placeholder="Selecciona producto a eliminar",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        page, index = self.values[0].split("|")
        index = int(index)

        product = PRODUCTS[page][index]

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⚠️ Confirmar eliminación",
                description=f"¿Seguro que quieres borrar **{product[0]}**?",
                color=discord.Color.red()
            ),
            view=ConfirmDeleteView(page, index)
        )

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, page, index):
        super().__init__(timeout=None)
        self.page = page
        self.index = index

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        product = PRODUCTS[self.page][self.index]
        PRODUCTS[self.page].pop(self.index)
        save_products(PRODUCTS)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🗑️ Eliminado",
                description=f"{product[0]} eliminado correctamente",
                color=discord.Color.green()
            ),
            view=None
        )

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(
            content="❌ Cancelado",
            embed=None,
            view=None
        )

# ========= checkinv ===================
@tree.command(name="checkinv", description="Ver tus invitaciones")
async def checkinv(interaction: discord.Interaction):
    invites = INVITES.get(str(interaction.user.id), 0)
    await interaction.response.send_message(
        f"📨 Tienes **{invites}** invitaciones.",
        ephemeral=True
    )

# ----------- interpretar duracion ---------------------
def parse_duration(duration):
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800
    }
    return int(duration[:-1]) * units[duration[-1]]

# ================== /sortear =====================

    async def update_giveaway_message(message, premio, ganadores, minimo, fin):
        participantes = SORTEOS.get(message.id, [])

        embed = discord.Embed(
            title="🎉 SORTEO",
            description=(
                f"**Premio:** {premio}\n"
                f"**Ganadores:** {ganadores}\n"
                f"**Finaliza:** <t:{int(fin.timestamp())}:R>\n"
                f"**Invitaciones mínimas:** {minimo}\n\n"
                f"👥 **Participantes actuales:** {len(participantes)}\n\n"
                "Recuerda tener pruebas de como has invitado a tus amigos al servidor!"
            ),
            color=discord.Color.gold()
        )

        await message.edit(embed=embed)

SORTEOS = {}

@tree.command(name="sortear", description="Crear un sorteo")
async def sortear(interaction: discord.Interaction,
                  duracion: str,
                  premio: str,
                  ganadores: int,
                  minimo_invitaciones: int):

    segundos = parse_duration(duracion)
    fin = discord.utils.utcnow() + timedelta(seconds=segundos)

    embed = discord.Embed(
        title="🎉 SORTEO",
        description=(
            f"**Premio:** {premio}\n"
            f"**Ganadores:** {ganadores}\n"
            f"**Finaliza:** <t:{int(fin.timestamp())}:R>\n"
            f"**Invitaciones mínimas:** {minimo_invitaciones}\n\n"
            f"👥 **Participantes actuales:** 0\n\n"
            "Recuerda tener pruebas de como has invitado a tus amigos al servidor!"
        ),
        color=discord.Color.gold()
    )

    msg = await interaction.channel.send(
        embed=embed,
        view=JoinGiveawayButton(None, minimo_invitaciones)
    )

    # guardar id real del mensaje en el view
    msg.components[0].children[0].view.message_id = msg.id

    await interaction.response.send_message("✅ Sorteo creado.", ephemeral=True)

    await asyncio.sleep(segundos)

    # seleccionar ganadores
    participantes = SORTEOS.get(msg.id, [])

    if not participantes:
        await interaction.channel.send("❌ No hay participantes válidos.")
        return

    winners = random.sample(
        [interaction.guild.get_member(i) for i in participantes if interaction.guild.get_member(i)],
        min(ganadores, len(participantes))
    )

    winner_mentions = ", ".join(w.mention for w in winners if w)

    await interaction.channel.send(
        f"🎉 Ganadores: {winner_mentions}\n🏆 Premio: **{premio}**"
    )


# ------------------------
# Gestionar productos
# ------------------------
@tree.command(name="gestionarproductos", description="Gestionar productos")
async def gestionar(interaction: discord.Interaction):

    admin_role = discord.utils.get(interaction.guild.roles, name="Administrador")
    if admin_role not in interaction.user.roles:
        await interaction.response.send_message("❌ No permiso", ephemeral=True)
        return

    class ManageView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="➕ Añadir", style=discord.ButtonStyle.success)
        async def add(self, interaction, button):
            await interaction.response.send_modal(AddProductModal())

        @discord.ui.button(label="🗑 Eliminar", style=discord.ButtonStyle.danger)
        async def delete(self, interaction, button):
            view = discord.ui.View()
            view.add_item(ProductSelectDelete())

            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🗑 Eliminar producto",
                    description="Selecciona un producto del menú",
                    color=discord.Color.red()
                ),
                view=view,
                ephemeral=True
            )

        @discord.ui.button(label="✏️ Editar", style=discord.ButtonStyle.primary)
        async def edit(self, interaction, button):
            await interaction.response.send_modal(EditProductModal())

    embed = discord.Embed(
        title="📦 Gestión de productos",
        description="Usa los botones para gestionar productos",
        color=discord.Color.blue()
    )

    for page_id, items in PRODUCTS.items():
        if not items:
            continue
        lista = "\n".join([f"• {p[0]} - {p[1]}€" for p in items])
        embed.add_field(name=PAGE_NAMES[page_id], value=lista, inline=False)

    await interaction.response.send_message(embed=embed, view=ManageView(), ephemeral=True)

class JoinGiveawayButton(discord.ui.View):
    def __init__(self, message_id, minimo):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.minimo = minimo

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):

        user_id = str(interaction.user.id)
        invites = INVITES.get(user_id, 0)

        if invites < self.minimo:
            await interaction.response.send_message(
                f"❌ Necesitas mínimo **{self.minimo} invitaciones**. Tienes **{invites}**.",
                ephemeral=True
            )
            return

        if self.message_id not in SORTEOS:
            SORTEOS[self.message_id] = []

        if interaction.user.id in SORTEOS[self.message_id]:
            await interaction.response.send_message(
                "❌ Ya estás participando.",
                ephemeral=True
            )
            return

        SORTEOS[self.message_id].append(interaction.user.id)

        await interaction.response.send_message(
            "✅ Te has unido al sorteo.",
            ephemeral=True
        )

        # 🔥 ACTUALIZAR EMBED
        await update_giveaway_message(
            interaction.message,
            "SORTEO",
            0,
            self.minimo,
            discord.utils.utcnow()
        )

# ---------------------------
# Vouchs
# ---------------------------
@tree.command(name="vouch", description="Enviar vouch")
@app_commands.describe(
    producto="Nombre del producto",
    estrellas="Número de estrellas (1-10)",
    opinion="Opinión"
)
async def vouch(interaction: discord.Interaction, producto: str, estrellas: int, opinion: str = None):

    if estrellas < 1 or estrellas > 10:
        await interaction.response.send_message("❌ Estrellas 1-10", ephemeral=True)
        return

    channel = bot.get_channel(VOUCH_CHANNEL_ID)

    embed = discord.Embed(title="🌟 Nuevo Vouch", color=discord.Color.blue())
    embed.add_field(name="👤 Usuario", value=interaction.user.mention, inline=False)
    embed.add_field(name="📦 Producto", value=producto, inline=False)
    embed.add_field(name="⭐ Estrellas", value=f"{'⭐' * estrellas}", inline=False)

    if opinion:
        embed.add_field(name="💬 Opinión", value=opinion, inline=False)

    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Vouch enviado", ephemeral=True)

# ---------------------------
# Comando principal del ticket
# ---------------------------
@bot.command()
async def t(ctx):
    embed = discord.Embed(
        title="🎟 Cludy Tickets",
        description="Selecciona una opción:",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed, view=MainTicketView())
    
# ---------------------------
# Borrar ticket con !del
# ---------------------------
@bot.command(name="del")
async def delete_ticket(ctx):
    admin_role = discord.utils.get(ctx.guild.roles, name="Administrador")

    # Verificar permisos
    if admin_role not in ctx.author.roles:
        await ctx.send("❌ No permiso.", delete_after=5)
        return

    # Verificar que el comando se usa en un ticket
    if not any(keyword in ctx.channel.name for keyword in ["ticket", "soporte", "pagado"]):
        await ctx.send("❌ Este comando solo puede usarse en tickets.", delete_after=5)
        return

    await ctx.send("🗑️ Cerrando ticket en 3 segundos...")
    await asyncio.sleep(3)
    await ctx.channel.delete()
@bot.event
async def on_member_join(member):
    guild = member.guild
    new_invites = await guild.invites()
    old_invites = GUILD_INVITES.get(guild.id, [])

    for invite in new_invites:
        for old in old_invites:
            if invite.code == old.code and invite.uses > old.uses:
                user_id = str(invite.inviter.id)
                INVITES[user_id] = INVITES.get(user_id, 0) + 1
                save_invites(INVITES)

    GUILD_INVITES[guild.id] = new_invites

# ---------------------------
# Ready
# ---------------------------
@bot.event
async def on_ready():
    await tree.sync()
    bot.add_view(TicketView())
    bot.add_view(MainTicketView())

    for guild in bot.guilds:
        GUILD_INVITES[guild.id] = await guild.invites()

    print("✅ Bot listo.")

# ---------------------------
# WEBHOOK INTERNO (RECIBE PAYPAL)
# ---------------------------
app = Flask(__name__)

@app.route("/paypal-webhook", methods=["POST"])
def paypal_webhook():
    data = request.json

    event_type = data.get("event_type")

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = data.get("resource", {})
        nota = resource.get("custom_id")

        if nota in PAGOS:
            pago = PAGOS[nota]

            if not pago["pagado"]:
                pago["pagado"] = True
                save_pagos(PAGOS)

                bot.loop.create_task(entregar_producto(pago))

    return "OK", 200


async def entregar_producto(pago):
    user = await bot.fetch_user(pago["user_id"])
    channel = bot.get_channel(pago["channel_id"])

    if user:
        await user.send(f"📦 Tu producto:\n{pago['link']}")

    if channel:
        await channel.send(
            f"✅ **Pago verificado automáticamente**\n"
            f"📦 Producto entregado:\n{pago['link']}"
        )


def run_flask():
    app.run(port=5001)


threading.Thread(target=run_flask).start()

bot.run(TOKEN)
