import json
import random
from typing import Optional
import discord
from discord.ext import commands

import time
import re
import async_cse # google

from bot import MetroBot
from utils.custom_context import MyContext
from utils.converters import DiscordCommand, ImageConverter
from utils.useful import Cooldown, Embed, chunkIt
from utils.calc_tils import NumericStringParser
from utils.json_loader import get_path, read_json

data = read_json("info")
or_api_token = data['openrobot_api_key']
google_token = data['google_token']

class WebhookConverter(commands.Converter):
  async def convert(self, ctx: commands.Context, argument: str) -> discord.Webhook:
    check = re.match(r"https://discord(?:app)?.com/api/webhooks/(?P<id>[0-9]{17,21})/(?P<token>[A-Za-z0-9\.\-\_]{60,68})", argument)
    if not check:
      raise commands.BadArgument("Webhook not found.")
    else:
        return check

class CodeBlock:
    missing_error = 'Missing code block. Please use the following markdown\n\\`\\`\\`language\ncode here\n\\`\\`\\`'
    def __init__(self, argument):
        try:
            block, code = argument.split('\n', 1)
        except ValueError:
            raise commands.BadArgument(self.missing_error)

        if not block.startswith('```') and not code.endswith('```'):
            raise commands.BadArgument(self.missing_error)

        language = block[3:]
        self.command = self.get_command_from_language(language.lower())
        self.source = code.rstrip('`').replace('```', '')

    def get_command_from_language(self, language):
        cmds = {
            'cpp': 'g++ -std=c++1z -O2 -Wall -Wextra -pedantic -pthread main.cpp -lstdc++fs && ./a.out',
            'c': 'mv main.cpp main.c && gcc -std=c11 -O2 -Wall -Wextra -pedantic main.c && ./a.out',
            'py': 'python3 main.cpp',
            'python': 'python3 main.cpp',
            'haskell': 'runhaskell main.cpp'
        }

        cpp = cmds['cpp']
        for alias in ('cc', 'h', 'c++', 'h++', 'hpp'):
            cmds[alias] = cpp
        try:
            return cmds[language]
        except KeyError as e:
            if language:
                fmt = f'Unknown language to compile for: {language}'
            else:
                fmt = 'Could not find a language to compile with.'
            raise commands.BadArgument(fmt) from e

info = read_json('info')
bitly_token = info['bitly_token']

def setup(bot: MetroBot):
    bot.add_cog(extras(bot))

class extras(commands.Cog, description='Extra commands for your use.'):
    def __init__(self, bot: MetroBot):
        self.bot = bot

    @property
    def emoji(self) -> str:
        return '<:mplus:904450883633426553>'

    @commands.command()
    async def whatcog(self, ctx: MyContext, *, command: DiscordCommand) -> discord.Message:
        """Show what cog a command belongs to."""
        return await ctx.send(f"`{command.qualified_name}` belongs to the `{command.cog.qualified_name.capitalize() if command.cog else 'No Category'}` category")

    @commands.command()
    async def length(self, ctx: MyContext, *, object: str) -> discord.Message:
        """Get the length of a string."""
        return await ctx.send(f"That string is `{len(object)}` characters long.")

    @commands.command(aliases=['calc'])
    async def calculate(self, ctx, *, formula : str):
        """
        Calculate an equation.

        **Keys:**
            exponentiation: `^`
            multiplication: `x` | `*`
            division: `/`
            addition: `+` | `-`
            integer: `+` | `-` `0 .. 9+`
            constants: `PI` | `E`

        **Functions:**
            sqrt, log, sin, cos, tan, arcsin, arccos,
            arctan, sinh, cosh, tanh, arcsinh, arccosh,
            arctanh, abs, trunc, round, sgn
        """

        formula = formula.replace('*','x')

        formula = formula.lower().replace('k', '000').replace('m','000000')
        try:
            start = time.perf_counter()
            answer = NumericStringParser().eval(formula)
            end = time.perf_counter()
            await ctx.check()
        except Exception as e:
            return await ctx.send(str(e))

        if int(answer) == answer:
            answer = int(answer)

        ping = (end - start) * 1000

        embed = Embed()
        embed.description = f'Input: `{formula}`\nOutput: `{answer:,}`'
        embed.set_footer(text=f'Calculated in {round(ping, 1)}ms')
        await ctx.send(embed=embed)


    def read_tags(self, ctx : MyContext):
        ids, tags = [], []

        DPY_GUILD = ctx.bot.get_guild(336642139381301249)
        for member in DPY_GUILD.humans:
            ids.append(member.id)
        
        cwd = get_path()
        with open(cwd+'/config/'+'tags.txt', 'r', encoding='utf8') as file:
            for line in file.read().split("\n"):
    
                id = line[-52:-32]
  
                try:
                    if int(id) not in ids:
                        tag = line[10:112]
                        
                        tags.append(str(tag))
                except:
                    continue
        
        return tags

    @commands.command(hidden=True)
    @commands.is_owner()  
    @commands.bot_has_permissions(send_messages=True)  
    async def tags(self, ctx : MyContext, per_page : int = 10):
        await ctx.check()
        result = await self.bot.loop.run_in_executor(None, self.read_tags, ctx)
        await ctx.paginate(result, per_page=per_page)
        return
        m = chunkIt(result, 20)

        for i in m:
            e = Embed()
            e.description = ', '.join(i)
            
            #await ctx.author.send(embed=e)


    @commands.command(name='shorten_url', aliases=['shorten'])
    @commands.check(Cooldown(2, 5, 3, 5, commands.BucketType.user))
    async def shorten_url(self, ctx: MyContext, *, url: str):
        """
        Shorten a long url.
        
        Powered by [Bitly API](https://dev.bitly.com/)
        """
        if not re.fullmatch(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', url):
            raise commands.BadArgument("That is not a vaild url.")

        await ctx.defer()

        params = {"access_token" : bitly_token, "longUrl" : url}
        async with self.bot.session.get("https://api-ssl.bitly.com/v3/shorten", params=params) as response:
            if response.status != 200:
                raise commands.BucketType("Bitly API returned a bad response. Please try again later.")

            data = await response.json()

        embed = Embed()
        embed.colour = discord.Colour.orange()
        embed.description = f'Your shortened url: {data["data"]["url"]}\nOriginal url: {url}'
        embed.set_author(name='URL Shortner')
        return await ctx.send(embed=embed)

    @commands.command(name='repl', aliases=['coliru'])
    @commands.check(Cooldown(1, 4, 1, 3, commands.BucketType.user))
    async def coliru(self, ctx: MyContext, *, code: CodeBlock):
        """Compile code through coliru."""

        payload = {
            'cmd' : code.command,
            'src' : code.source
        }

        data = json.dumps(payload)

        async with ctx.typing():
            async with self.bot.session.post('http://coliru.stacked-crooked.com/compile', data=data) as response:
                if response.status != 200:
                    return await ctx.send("Coliru did not response in time.")

                output = await response.text(encoding='utf-8')

                if len(output) < 1992:
                    return await ctx.send(f'```\n{output}\n```')

                url = await self.bot.mystbin_client.post(output)
                return await ctx.send("Output was too long: %s" % url)

    @commands.command(name='nsfw-check')
    @commands.check(Cooldown(2, 10, 2, 8, commands.BucketType.user))
    async def nsfw_check(self, ctx: MyContext, *, image: Optional[str]):
        """
        Check for NSFW in an image.
        
        This command is powered by [OpenRobo API](https://api.openrobot.xyz/api/docs#operation/do_nsfw_check_api_nsfw_check_get)
        """

        url = (
            await ImageConverter().convert(ctx, image)
            or ctx.author.display_avatar.url
        )

        async with self.bot.session.get("https://api.openrobot.xyz/api/nsfw-check", headers={'Authorization' : or_api_token},params = {'url' : url}) as response:
            if response.status != 200:
                return await ctx.send("Openrobot API returned a bad result.")

            response_data = await response.json()
        
        embed = discord.Embed()
        embed.description = f"Is NSFW: {self.bot.emotes['check'] if response_data['nsfw_score'] > 0.25 else self.bot.emotes['cross']}"
        embed.add_field(name=f'{self.bot.emotes["online"]} Safe Score', value=f"`{round(100 - (response_data['nsfw_score']*100), 2)}%`")
        embed.add_field(name=f'{self.bot.emotes["dnd"]} Unsafe Score', value=f"`{round(response_data['nsfw_score']*100, 2)}%`")
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.command(name='poll')
    @commands.check(Cooldown(1, 30, 1, 30, commands.BucketType.member))
    async def poll(self, ctx: MyContext, *, question: commands.clean_content):
        """
        Simple yes/no poll with reactions.
        
        This command can be used regardless of permissions.

        If you an admin that doesn't like this please use
        `config disable ~ poll` to disable this command.
        """

        await ctx.message.delete(silent=True)

        message = await ctx.send(f"**{ctx.author}** is asking a question: \n> {question}", reply=False)
        await message.add_reaction('\U0001f44d')
        await message.add_reaction('\U0001f44e')

    @commands.command()
    @commands.check(Cooldown(2, 10, 2, 8, commands.BucketType.user))
    async def google(self, ctx: MyContext, *, query: str):
        """Search google using it's API."""

        async with ctx.typing():
            start = time.perf_counter()
            results = await self.bot.google_client.search(query, safesearch=False)
            end = time.perf_counter()

            ping = (end - start) * 1000

            embed = discord.Embed(color=ctx.color)
            embed.set_author(name=f'Google search: {query}')
            for result in results[:5]:
                embed.add_field(name=result.title, value=f'{result.url}\n{result.description}', inline=False)
            embed.set_footer(text=f'Queried in {round(ping, 2)} milliseconds. | Safe Search: Disabled')
            return await ctx.send(embed=embed)
            