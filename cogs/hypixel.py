import discord
from discord.ext import commands
from discord.ext.commands.core import command
from cogs.utility import utility

from utils.custom_context import MyContext
from utils.json_loader import read_json, write_json
from bot import MetroBot
from utils.useful import Embed

info_file = read_json('info')
hypixel_api_key = info_file["hypixel_api_key"]

def setup(bot):
    bot.add_cog(hypixel(bot))

class hypixel(commands.Cog, description='<:hypixel:912575998380355626> Get stats from hypixel api'):
    def __init__(self, bot : MetroBot):
        self.bot = bot

        self.profiles_cache = {}

    @commands.command(name='mc_uuid', aliases=['uuid'])
    @commands.cooldown(1, 5, commands.cooldowns.BucketType.default)
    async def mc_uuid(self, ctx : MyContext, *, username : str):
        """Get the UUID and avatar of a minecraft username from Minecraft API"""

        async with self.bot.session.get(f"https://api.mojang.com/users/profiles/minecraft/{username}") as s:
            if s.status == 204:
                raise commands.BadArgument('That is not a vaild minecraft username!')
            elif s.status != 200:
                raise commands.BadArgument('Something went wrong please contact my owner.')

            res = await s.json()

            user = res["name"]
            uuid = res["id"]

            embed = Embed()
            embed.add_field(name=f'Username: {user}', value=f'**UUID:** `{uuid}`')
            embed.set_image(url=f'https://crafatar.com/avatars/{uuid}?size=128&overlay=true')

            return await ctx.send(embed=embed)


    @commands.command(aliases=['bz'])
    async def bazzar(self, ctx : MyContext, *, item : str):
        """
        Get item data of an item in the bazzar.
        This is powered by Hypixel API.

        You can find a full list of items here:
        https://gist.github.com/103f740138c9759c1fab06e0173e58eb
        Note at you may omit the capitalization and underscores
        """
        async with ctx.typing():
            async with self.bot.session.get(f"https://api.hypixel.net/skyblock/bazaar") as s:
                if s.status == 503:
                    raise commands.BadArgument('The leaderboard data has not yet been populated and should be available shortly.')
                if s.status != 200:
                    raise commands.BadArgument('Something went wrong please contact my owner.')

                res = await s.json()

                try:
                    item = res["products"][item.upper().replace(" ", "_")]
                except KeyError:
                    raise commands.BadArgument(f"Your item was not found!\nYou can get a full list of the items by typing `{ctx.prefix}help bz`")

                quick_sum = item["quick_status"]

                embed = Embed()
                embed.title = quick_sum["productId"]
                embed.add_field(
                    name='Sell Stats',
                    value=f'Sell Price: `{round(quick_sum["sellPrice"], 1):,}`'\
                        f'\nSell Volume: `{quick_sum["sellVolume"]:,}`'\
                        f'\nSell Orders: `{quick_sum["sellOrders"]}`'\
                        f'\nSell Moving Weekly: `{quick_sum["sellMovingWeek"]:,}`',
                    inline=False
                )
                embed.add_field(
                    name='Buy Stats',
                    value=f'Buy Price: `{round(quick_sum["buyPrice"], 1):,}`'\
                        f'\nBuy Volume: `{quick_sum["buyVolume"]:,}`'\
                        f'\nBuy Orders: `{quick_sum["buyOrders"]}`'\
                        f'\nBuy Moving Weekly: `{quick_sum["buyMovingWeek"]:,}`',
                    inline=False
                )
                embed.set_footer(text='Powered by Hypixel API.')
                return await ctx.send(embed=embed)



    @commands.command()
    async def profiles(self, ctx : MyContext, *, username : str):
        """
        Get all the profiles of a username.
        Powered by Hypixel API.
        """

        async with ctx.typing():
            async with self.bot.session.get(f"https://api.hypixel.net/player?key=" + hypixel_api_key + "&name=" + username) as s:

                if s.status == 429:
                    raise commands.BadArgument("The request limit for this command has been reached. Please try again later.")

                if s.status == 403:
                    raise commands.BadArgument("Invaild API Key. Please contact my owner.")

                if s.status != 200:
                    raise commands.BadArgument('Something went wrong please contact my owner.')

                res = await s.json()
                
                to_paginate = []
                for a, b in list(res['player']['stats']['SkyBlock']['profiles'].items()):
                    to_paginate.append(f"`{b['profile_id']}` - {b['cute_name']}")


                embed = Embed()
                embed.title = f'{res["player"]["displayname"]}\'s profiles'
                embed.description = '\n'.join(to_paginate)
                embed.set_footer(text='Powered by Hypixel API.')

                return await ctx.send(embed=embed)


    




