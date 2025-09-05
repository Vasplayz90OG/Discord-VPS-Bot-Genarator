# bot.py
import os
import json
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
from vps_manager import create_vps, delete_vps, list_vps, get_vps_info

# load env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
CREDITS = os.getenv("CREDITS", "Vasplayz90")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN missing in environment (.env)")

# bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# persistent storage file
DATA_FILE = "data.json"
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        DATA = json.load(f)
else:
    DATA = {"vps": {}, "admins": [], "banned_vps": [], "banned_users": []}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(DATA, f, indent=2)

def is_owner(user_id):
    return user_id == OWNER_ID

def is_admin(user_id):
    return is_owner(user_id) or str(user_id) in DATA.get("admins", [])

@bot.event
async def on_ready():
    print(f"✅ Bot ready. Logged in as {bot.user} — Credits: {CREDITS}")
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Warning: failed to sync commands:", e)

# ---------------- Commands ----------------

@bot.tree.command(name="deploy", description="Create a VPS; details will be DM'd to you.")
@app_commands.describe(os_image="Docker image name (or fake)", ram_mb="RAM (e.g. 512m)", disk_gb="Disk (informational)")
async def deploy(interaction: discord.Interaction, os_image: str, ram_mb: str, disk_gb: str):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    if str(user_id) in DATA.get("banned_users", []):
        await interaction.followup.send("You are banned from creating VPS.", ephemeral=True)
        return

    try:
        info = create_vps(owner_id=str(user_id), os_image=os_image, ram=ram_mb, disk=disk_gb)
    except Exception as e:
        await interaction.followup.send(f"Failed to create VPS: {e}", ephemeral=True)
        return

    vps_id = info["id"]
    DATA["vps"][vps_id] = {"owner": str(user_id), "os": os_image, "ram": ram_mb, "disk": disk_gb}
    save_data()

    # DM with credentials & credits text (cannot be changed by users)
    cred_text = (
        f"**VPS Created ✅**\n"
        f"ID: `{vps_id}`\n"
        f"IP: `{info['ip']}`\n"
        f"SSH Port: `{info['ssh_port']}`\n"
        f"User: `{info['username']}`\n"
        f"Password: `{info['password']}`\n\n"
        f"Credits: {CREDITS} — Watching ArizNodes Plz Make"
    )

    try:
        await interaction.user.send(cred_text)
        await interaction.followup.send("VPS created — details sent to your DM.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Could not DM you — enable DMs from server members.", ephemeral=True)

@bot.tree.command(name="deletevps", description="Delete a VPS you own (or admins).")
@app_commands.describe(vps_id="VPS ID to delete")
async def deletevps(interaction: discord.Interaction, vps_id: str):
    user_id = interaction.user.id
    vmeta = DATA.get("vps", {}).get(vps_id)
    if not vmeta:
        await interaction.response.send_message("VPS not found.", ephemeral=True)
        return
    if vmeta["owner"] != str(user_id) and not is_admin(user_id):
        await interaction.response.send_message("You don't have permission to delete this VPS.", ephemeral=True)
        return

    ok = delete_vps(vps_id)
    if ok:
        DATA["vps"].pop(vps_id, None)
        save_data()
        await interaction.response.send_message(f"VPS {vps_id} deleted.", ephemeral=True)
    else:
        await interaction.response.send_message("Failed to delete VPS from backend.", ephemeral=True)

@bot.tree.command(name="ban_vps", description="Owner only: ban or unban a VPS ID (prevents use).")
@app_commands.describe(vps_id="VPS ID", ban="true to ban, false to unban")
async def ban_vps(interaction: discord.Interaction, vps_id: str, ban: bool):
    user_id = interaction.user.id
    if not is_owner(user_id):
        await interaction.response.send_message("Only the owner can ban/unban vps.", ephemeral=True)
        return
    if ban:
        if vps_id not in DATA.get("banned_vps", []):
            DATA.setdefault("banned_vps", []).append(vps_id)
        await interaction.response.send_message(f"VPS {vps_id} banned.", ephemeral=True)
    else:
        if vps_id in DATA.get("banned_vps", []):
            DATA["banned_vps"].remove(vps_id)
        await interaction.response.send_message(f"VPS {vps_id} unbanned.", ephemeral=True)
    save_data()

@bot.tree.command(name="list", description="List VPS (owner/admin sees all; members see own).")
async def list_cmd(interaction: discord.Interaction):
    user_id = interaction.user.id
    items = []
    for vid, meta in DATA.get("vps", {}).items():
        if meta["owner"] == str(user_id) or is_admin(user_id):
            items.append(f"{vid} — owner: {meta['owner']} — os: {meta['os']} — ram: {meta['ram']}")
    if not items:
        await interaction.response.send_message("No VPS found.", ephemeral=True)
    else:
        await interaction.response.send_message("\n".join(items), ephemeral=True)

@bot.tree.command(name="add_admin", description="Owner only: add an admin by Discord ID.")
@app_commands.describe(user_id="Discord user ID to add as admin")
async def add_admin(interaction: discord.Interaction, user_id: str):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only owner can add admins.", ephemeral=True)
        return
    if user_id in DATA.get("admins", []):
        await interaction.response.send_message("User is already admin.", ephemeral=True)
        return
    DATA.setdefault("admins", []).append(user_id)
    save_data()
    await interaction.response.send_message(f"Added admin {user_id}.", ephemeral=True)

@bot.tree.command(name="manage_vps", description="Show/manage a VPS (owner/admin/member).")
@app_commands.describe(vps_id="VPS ID to manage")
async def manage_vps(interaction: discord.Interaction, vps_id: str):
    user_id = interaction.user.id
    meta = DATA.get("vps", {}).get(vps_id)
    if not meta:
        await interaction.response.send_message("VPS not found.", ephemeral=True)
        return
    if meta["owner"] != str(user_id) and not is_admin(user_id):
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    info = get_vps_info(vps_id)
    if not info:
        await interaction.response.send_message("Backend info not found.", ephemeral=True)
        return
    await interaction.response.send_message(f"VPS {vps_id} info (DM’d): IP {info['ip']} SSH:{info['ssh_port']}", ephemeral=True)
    try:
        await interaction.user.send(
            f"VPS {vps_id} details:\nIP: `{info['ip']}`\nSSH Port: `{info['ssh_port']}`\nUser: `{info['username']}`\nPassword: `{info['password']}`\nCredits: {CREDITS} — Watching ArizNodes Plz Make"
        )
    except discord.Forbidden:
        pass

@bot.tree.command(name="clear", description="Owner only: delete all VPS (use with extreme caution).")
async def clear_cmd(interaction: discord.Interaction):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only owner can clear all VPS.", ephemeral=True)
        return
    vids = list(DATA.get("vps", {}).keys())
    failed = []
    for v in vids:
        if not delete_vps(v):
            failed.append(v)
        else:
            DATA["vps"].pop(v, None)
    save_data()
    await interaction.response.send_message(f"Cleared. Failed: {failed}", ephemeral=True)

# run
if __name__ == "__main__":
    bot.run(TOKEN)
