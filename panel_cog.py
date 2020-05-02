import discord
from discord.ext import tasks, commands
from pydactyl import PterodactylClient
from config import *
import logging
from urllib3.exceptions import NewConnectionError
from socket import gaierror
from requests.exceptions import ConnectionError, HTTPError
from time import time
from os.path import dirname, realpath
import asyncio
import concurrent.futures
import functools

class panel_cog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pclient = PterodactylClient(config_panel_url, config_panel_token)
        # possible: offline, online, starting, stopping, error
        self.server_power_status = "offline"
        self.current_vote_action = None
        self.voters = []
        self.voting_time_start = 0
        self.was_empty_last_check = False
        self.logger = logging.getLogger("tonymc.panel_cog")
        self.periodically_get_status.add_exception_type(NewConnectionError)
        self.periodically_get_status.add_exception_type(gaierror)
        self.periodically_get_status.add_exception_type(ConnectionError)
        self.periodically_get_status.add_exception_type(HTTPError)
        self.periodically_get_status.start()
        self.has_motion_expired.start()
        if config_shutdown_empty_server:
            self.check_if_should_turn_off.start()

    @tasks.loop(seconds=10.0)
    async def has_motion_expired(self):
        if self.current_vote_action is not None:
            if time() - self.voting_time_start >= config_vote_timeout:
                self.logger.info("Motion {0} expired.".format(
                    self.current_vote_action))
                await self.clear_voting()

    @has_motion_expired.before_loop
    async def before_motion(self):
        self.logger.debug("Waiting for bot to be ready... (Motion Expiration)")
        await self.bot.wait_until_ready()

    async def block_to_async(self, partial: functools.partial):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial)

    @tasks.loop(seconds=config_ping_time)
    async def periodically_get_status(self):
        self.logger.debug("Getting panel status (Panel)")
        try:
            fn = functools.partial(self.pclient.client.get_server_utilization, config_server_id)
            self.server_status = await self.block_to_async(fn)

            if self.server_status['state'] == "on":
                self.server_power_status = "online"
            elif self.server_status['state'] == "off":
                self.server_power_status = "offline"
            else:
                self.server_power_status = self.server_status['state']

            self.logger.debug("Panel status succesfully recieved")

        except (NewConnectionError, gaierror, ConnectionError):
            self.logger.error("Can't connect to panel! Bad URL?")
            self.server_power_status = "error"
        except HTTPError as e:
            if e.response.status_code == 403:
                self.logger.error("Can't connect to panel! Bad API Key!")
            self.server_power_status = "error"

        self.logger.debug("Done with Panel.")

    @periodically_get_status.before_loop
    async def before_status(self):
        self.logger.debug("Waiting for bot to be ready... (Panel Status)")
        await self.bot.wait_until_ready()

    async def get_cpu_and_ram(self):
        if self.server_power_status == "online":
            return self.server_status['cpu']['current'], self.server_status['memory']['current']
        else:
            return 0, 0

    @tasks.loop(minutes=config_server_auto_time)
    async def check_if_should_turn_off(self):
        self.logger.debug("Checking if server needs to be turned off")
        if self.server_power_status == "online":
            mcstatus_info = self.bot.get_cog("mcstatus_cog")
            if mcstatus_info is not None:
                current, max = await mcstatus_info.get_players_and_max()
                if current != 0:
                    self.was_empty_last_check = False
                    self.logger.debug("Players detected. Not touching server.")
                else:
                    if self.was_empty_last_check == True:
                        self.logger.info("Automatically stopping empty server")
                        await self.power_action("stop")
                        self.was_empty_last_check = False
                    else:
                        self.logger.debug(
                            "No players detected. Waiting for one more loop then shutting down server")
                        self.was_empty_last_check = True
            else:
                self.logger.error("Wasn't able to get MCStatus Cog...")
        else:
            self.logger.debug("Server isn't on. No reason.")
            self.was_empty_last_check = False

    @check_if_should_turn_off.before_loop
    async def before_check(self):
        self.logger.debug("Waiting for bot to be ready... (Auto Shutdown)")
        await self.bot.wait_until_ready()

    @commands.group(aliases=["off", "turn_off", "stop", "shutdown"])
    async def server_off(self, ctx):
        """Vote to turn off the server."""
        if ctx.invoked_subcommand is None:
            if ctx.message.author.id in config_admin_users:
                self.logger.info("{0} ({1}) admin'd server off.".format(
                    ctx.message.author.name, ctx.message.author.id))
                await self.power_action("stop")
                await ctx.message.add_reaction("👍")
            else:
                if await self.voting(ctx, "stop"):
                    self.logger.info("Motion Passed: stop")
                    await self.power_action("stop")

    @commands.group(aliases=["on", "turn_on", "start", "boot"])
    async def server_on(self, ctx):
        """Vote to turn on the server."""
        if ctx.invoked_subcommand is None:
            if ctx.message.author.id in config_admin_users:
                self.logger.info("{0} ({1}) admin'd server on.".format(
                    ctx.message.author.name, ctx.message.author.id))
                await self.power_action("start")
                await ctx.message.add_reaction("👍")
            else:
                if await self.voting(ctx, "start"):
                    self.logger.info("Motion Passed: start")
                    await self.power_action("start")

    @server_off.command()
    async def kill(self, ctx):
        """Kill the server immediately. Admin Only. Can cause corruption."""
        if ctx.message.author.id in config_admin_users:
            self.logger.warn("{0} ({1}) killed server.".format(
                ctx.message.author.name, ctx.message.author.id))
            await self.power_action("kill")
            await ctx.message.add_reaction("👍")
        else:
            embed = discord.Embed(title="Server Status",
                                  color=config_embed_color)

            filepath = "{0}/images/sad.png".format(dirname(realpath(__file__)))
            file = discord.File(filepath, "icon.png")
            embed.add_field(name="Access Denied",
                            value="Nah, son.", inline=False)
            embed.set_image(url="attachment://icon.png")
            embed.set_footer(text=config_custom_footer)

            await ctx.send(file=file, embed=embed)

    @commands.command(aliases=["restart", "reboot"])
    async def server_restart(self, ctx):
        """Vote to restart the server."""
        if ctx.message.author.id in config_admin_users:
            self.logger.info("{0} ({1}) admin'd server reboot.".format(
                ctx.message.author.name, ctx.message.author.id))
            await self.power_action("restart")
            await ctx.message.add_reaction("👍")
        else:
            if await self.voting(ctx, "restart"):
                self.logger.info("Motion Passed: restart")
                await self.power_action("restart")

    async def power_action(self, action):
        if action == "start":
            if self.server_power_status == "offline":
                self.server_power_status = "starting"
        elif action == "stop":
            if self.server_power_status == "online":
                self.server_power_status = "stopping"
        elif action == "restart":
            if self.server_power_status == "offline":
                self.server_power_status = "starting"
            if self.server_power_status == "online":
                self.server_power_status = "stopping"
        fn = functools.partial(self.pclient.client.send_power_action, config_server_id, action)
        await self.block_to_async(fn)
        mcstatus_info = self.bot.get_cog("mcstatus_cog")
        if mcstatus_info is not None:
            await mcstatus_info.change_discord_status(self.server_power_status)
        else:
            self.logger.error("Unable to get MCStatus cog in power_action")


    @commands.command()
    async def cmd(self, ctx, *, arg):
        if ctx.message.author.id in config_superadmin_users:
            if self.server_power_status == "online":
                fn = functools.partial(self.pclient.client.send_console_command, config_server_id, arg)
                await self.block_to_async(fn)
                await ctx.message.add_reaction("👍")
            else:
                await ctx.message.add_reaction("❌")

    async def voting(self, ctx, motion):
        if self.current_vote_action is None:
            self.voting_time_start = time()
            self.current_vote_action = motion
            self.voters.append(ctx.message.author.id)
            if config_votes_needed <= 1:
                await ctx.send('Motion "{0}" passed!'.format(motion))
                await self.clear_voting()
                return True
            else:
                await ctx.send('You need **{0}** more people to type the same command!'.format(config_votes_needed-len(self.voters)))
                return False
        else:
            if motion != self.current_vote_action:
                await ctx.send('This motion does not match the current motion. Please wait for the previous motion to expire, or vote for that.')
                return False
            else:
                if ctx.message.author.id not in self.voters:
                    self.voters.append(ctx.message.author.id)
                    if len(self.voters) >= config_votes_needed:
                        await ctx.send('Motion "{0}" passed!'.format(motion))
                        await self.clear_voting()
                        return True
                    else:
                        await ctx.send('You need **{0}** more people to type the same command!'.format(config_votes_needed-len(self.voters)))
                        return False
                else:
                    await ctx.send('You have already voted on the current motion! Please wait for the current motion to expire or pass.')
                    return False

    async def clear_voting(self):
        self.voting_time_start = 0
        self.current_vote_action = None
        self.voters.clear()
