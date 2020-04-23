#!/home/tony/python/tonymc/venv/bin/python3

import discord
from discord.ext import tasks, commands
#from mcstatus import MinecraftServer
import random
from panel_cog import panel_cog
from mcstatus_cog import mcstatus_cog
import logging
from io import BytesIO
from config import *
from os.path import dirname, realpath

#server = MinecraftServer(config_ip, config_port)

#pclient = PterodactylClient(config_panel_url, config_panel_token)

description = '''Bot written by Tony to start/stop the Minecraft server based on current activity and user requests for server uptime.'''

bot = commands.Bot(command_prefix=config_command_prefix,
                   description=description)
# https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#discord.ext.commands.when_mentioned_or

bot.remove_command('help')
logger = logging.getLogger("tonymc")


@bot.event
async def on_ready():
    logger.info("Logged in as {0} with ID: {1}".format(
        bot.user.name, bot.user.id))

@bot.command()
async def help(ctx):
    embed = embed = discord.Embed(title="Bot Help", color=config_embed_color)
    embed.add_field(name="help", value="This command right here!", inline=False)
    embed.add_field(name="restart", value="(aliases: server_restart, reboot)\nRestarts the server immediately after vote passes", inline=False)
    embed.add_field(name="stop", value="(aliases: server\_off, off, turn\_off, shutdown)\nWill stop the server immediately after vote passes\n\nAdmins can run `{0}stop kill` to kill the server. __Do not kill unless absolutely necessary__".format(config_command_prefix), inline=False)
    embed.add_field(name="start", value="(aliases: server\_on, on, turn\_on)\nWill start the server immediately after vote passes", inline=False)
    embed.add_field(name="status", value="Check and return the current (last known) status of the server.\nAlso shows currently connected players", inline=False)
    embed.add_field(name="How voting works", value="When someone types in a command (e.g. `{0}restart` or `{0}on`), it will start a vote for **{1}** seconds. If in that time a total of **{2}** people type the same command, it will do that action!".format(config_command_prefix, config_vote_timeout, config_votes_needed), inline=False)
    if config_shutdown_empty_server:
        embed.add_field(name="Auto shutdown", value="This bot checks every so often to see if the server is empty. If it is, it will be automatically shut down.", inline=False)
    embed.set_footer(text="config")
    await ctx.send(embed=embed)


@bot.command()
async def status(ctx):
    """Check and return the current (last known) status of the server."""
    embed = discord.Embed(title="Server Status", color=config_embed_color)
    mcstatus_info = bot.get_cog("mcstatus_cog")
    panel_info = bot.get_cog("panel_cog")
    current_status = await get_status()
    # Default icon in case no other image is set
    filepath = "{0}/images/owo.png".format(dirname(realpath(__file__)))
    file = discord.File(filepath, "icon.png")
    if mcstatus_info is not None and panel_info is not None:
        if current_status == "online":
            if panel_info.server_power_status == "online":
                cpu, ram = await panel_info.get_cpu_and_ram()
                cpu = "{0}%".format(cpu)
                ram = "{0}MB".format(ram)
                embed.add_field(name="CPU", value=cpu, inline=True)
                embed.add_field(name="RAM", value=ram, inline=True)
            if mcstatus_info.server_power_status == "online":
                fake_file = BytesIO(mcstatus_info.decoded_favicon)
                file = discord.File(fake_file, "icon.png")
                current, max = await mcstatus_info.get_players_and_max()
                full_value = "{0}/{1} Players".format(current, max)
                if current > 0:
                    full_value += "\n-----"
                    for player in mcstatus_info.server_status.players.sample:
                        full_value += "\n{0}".format(player.name)
                embed.add_field(name="Players", value=full_value, inline=False)
        else:
            if current_status == "starting":
                embed.add_field(name="Server Starting", value="Please wait while the server boots.", inline=False)
            elif current_status == "stopping":
                embed.add_field(name="Server Stopping", value="Please wait while the server shuts down.", inline=False)
                filepath = "{0}/images/uwu.png".format(dirname(realpath(__file__)))
                file = discord.File(filepath, "icon.png")
            else:
                filepath = "{0}/images/sad.png".format(dirname(realpath(__file__)))
                file = discord.File(filepath, "icon.png")
                example_command = "You can type `{0}on` (or its aliases) to start the server yourself!".format(config_command_prefix)
                embed.add_field(name="Server Offline", value=example_command, inline=False)
    else:
        logger.error("Either MCStatus or Panel cog was unable to talk!")
        embed.add_field(name="Internal Bot Error!", value="Can't talk to panel?", inline=False)
        filepath = "{0}/images/sad.png".format(dirname(realpath(__file__)))
        file = discord.File(filepath, "icon.png")
    
    embed.set_thumbnail(url="attachment://icon.png")
    embed.set_footer(
        text=config_custom_footer)
    # await self.bot.say(embed=embed)

    response = await ctx.send(file=file, embed=embed)
    #await bot.change_presence(activity=discord.Game("hi"), status=discord.Status.dnd)

async def get_status():
    mcstatus_info = bot.get_cog("mcstatus_cog")
    panel_info = bot.get_cog("panel_cog")
    if mcstatus_cog is not None and panel_cog is not None:
        if mcstatus_info.server_power_status != "online":
            acceptable_panel_statuses = ["offline", "online", "starting", "stopping", "error"]
            if panel_info.server_power_status in acceptable_panel_statuses:
                return panel_info.server_power_status
        else:
            return "online"


#status = server.status()
# for pl in status.players.sample:
#    print(pl.name)
#print("The server has {0} players and replied in {1} ms".format(status.players, status.latency))
# print(pclient.client.list_servers())



if __name__ == "__main__":
    # Configuring logging
    logger.setLevel(logging.DEBUG)
    filepath = "{0}/bot.log".format(dirname(realpath(__file__)))
    file_handler = logging.FileHandler(filepath)
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    log_formatter = logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    file_handler.setFormatter(log_formatter)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    bot.add_cog(mcstatus_cog(bot, get_status))
    bot.add_cog(panel_cog(bot))
    bot.run(config_discord_token)
