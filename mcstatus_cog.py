import discord
from discord.ext import tasks, commands
from config import *
import logging
from mcstatus import MinecraftServer
import base64
from io import BytesIO


class mcstatus_cog(commands.Cog):
    def __init__(self, bot: commands.Bot, get_status):
        self.bot = bot
        self.get_status = get_status
        self.logger = logging.getLogger("tonymc.mcstatus_cog")
        self.mc_server = MinecraftServer(config_ip, config_port)
        self.server_status = None
        self.favicon = None
        # possible: offline, whitelist (prob not), online
        self.server_power_status = "offline"
        self.periodically_get_status.add_exception_type(ConnectionError)
        self.periodically_get_status.add_exception_type(IOError)
        self.periodically_get_status.add_exception_type(ValueError)
        self.periodically_get_status.start()

    @tasks.loop(seconds=config_ping_time)
    async def periodically_get_status(self):
        self.logger.debug("Starting to get server status (MCStatus)")
        try:
            self.server_status = self.mc_server.status()
        except (ConnectionError, IOError, ValueError):
            self.logger.debug(
                "Server was not on - Or at least some kind of connection issue...")
            self.server_power_status = "offline"
        else:
            self.logger.debug("Server was on! Populating variables.")
            base_favicon = self.server_status.favicon
            # Add correct padding to favicon, otherwise the base64 library refuses to decode it.
            # https://stackoverflow.com/a/2942039
            base_favicon += "=" * ((4 - len(base_favicon) % 4) % 4)
            # Additionally, it doesn't seem to remove the type header, causing a corrupted image to be created.
            base_favicon = base_favicon.replace("data:image/png;base64,", "")
            self.decoded_favicon = base64.b64decode(base_favicon)
            self.server_power_status = "online"
        await self.change_discord_status()

    @periodically_get_status.before_loop
    async def before_status(self):
        self.logger.debug("Waiting for bot to be ready... (Server Status)")
        await self.bot.wait_until_ready()

    async def change_discord_status(self):
        game = None
        status = None
        server_status = await self.get_status()
        if server_status == "offline":
            game = discord.Game("Server Offline")
            status = discord.Status.dnd
        elif server_status == "online":
            current, max = await self.get_players_and_max()
            game = discord.Game("{0}/{1} Players".format(current, max))
            if current == 0:
                status = discord.Status.idle
            else:
                status = discord.Status.online
        elif server_status == "starting":
            game = discord.Game("Server Starting")
            status = discord.Status.idle
        elif server_status == "stopping":
            game = discord.Game("Server Stopping")
            status = discord.Status.dnd
        else:
            game = discord.Game("Unknown Error")
            status = discord.Status.idle
        await self.bot.change_presence(status=status, activity=game)
        self.logger.debug(
            "Changed presence to: {0}, {1}".format(game, status))

    async def get_players_and_max(self):
        if self.server_power_status == "online":
            return self.server_status.players.online, self.server_status.players.max
        else:
            return 0, 0
