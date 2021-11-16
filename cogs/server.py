from operator import add
import re
from typing import Optional
import discord
from discord.ext import commands

from collections import Counter
import asyncio
import argparse
import shlex

from utils.custom_context import MyContext

class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)

class server(commands.Cog, description=':wrench: Module for server management.'):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def do_removal(ctx : MyContext, limit : int, predicate, *, before = None, after = None, bulk : bool = True):
        if limit > 2000:
            raise commands.BadArgument(f'Too many messages to search. ({limit}/2000)')

        async with ctx.typing():
            if before is None:
                before = ctx.message
            else:
                before = discord.Object(id=before)
            
            if after is not None:
                after = discord.Object(id=after)

            try:
                deleted = await ctx.channel.purge(limit=limit, before=before, after=after, check=predicate, bulk=bulk)
            except discord.Forbidden:
                raise commands.BadArgument(f'I do not have the `manage_messages` permission to delete messages.')
            except discord.HTTPException as e:
                return await ctx.send(f'Error: {e}')

            spammers = Counter(m.author.display_name for m in deleted)
            deleted = len(deleted)
            messages = [f'{deleted} message{" was" if deleted == 1 else "s were"} removed.']
            if deleted:
                messages.append('')
                spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
                messages.extend(f'**{name}**: {count}' for name, count in spammers)

            to_send = '\n'.join(messages)

            if len(to_send) > 2000:
                await ctx.send(f'Successfully removed {deleted} messages.', delete_after=7)
            else:
                await ctx.send(to_send, delete_after=7)




    @commands.group(
        name='purge',
        aliases=['clear', 'clean', 'remove'],
        invoke_without_command=True
    )
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx : MyContext, search : Optional[int]):
        """
        Remove messages that meet a certain criteria.
        
        If you run this without sub-commands it will remove all messages that are not pinned to the channel.
        Use "remove all <amount>" to remove all messages inculding pinned ones.
        """

        if search is None:
            return await ctx.help()

        await self.do_removal(ctx, search, lambda e: not e.pinned)
        
    @purge.command(name='embeds', aliases=['embed'])
    @commands.has_permissions(manage_messages=True)
    async def purge_embeds(self, ctx : MyContext, search : int):
        """Remove messages that have embeds in them."""
        await self.do_removal(ctx, search, lambda e: len(e.embeds))

    @purge.command(name='files', aliases=['attachments'])
    @commands.has_permissions(manage_messages=True)
    async def purge_files(self, ctx : MyContext, search : int):
        """Remove messages that have files in them."""
        await self.do_removal(ctx, search, lambda e: len(e.attachments))

    @purge.command(name='images')
    @commands.has_permissions(manage_messages=True)
    async def purge_images(self, ctx : MyContext, search : int):
        """Remove messages that have embeds or attachments."""
        await self.do_removal(ctx, search, lambda e: len(e.embeds) or len(e.attachments))

    @purge.command(name='all')
    @commands.has_permissions(manage_messages=True)
    async def purge_all(self, ctx : MyContext, search : int):
        """Remove all messages."""
        await self.do_removal(ctx, search, lambda e: True)

    @purge.command(name='user', aliases=['member'])
    @commands.has_permissions(manage_messages=True)
    async def purge_user(self, ctx : MyContext, member : discord.Member, search : int):
        """Remove all messages sent by that member."""
        await self.do_removal(ctx, search, lambda e: e.author == member)

    @purge.command(name='contains',aliases=['has'])
    @commands.has_permissions(manage_messages=True)
    async def purge_contains(self, ctx : MyContext, *, text : str):
        """
        Remove all messages containing a substring.
        Must be at least 3 characters long.
        """
        if len(text) < 3:
            await ctx.send(f'The substring must be at least 3 characters.')
        else:
            await self.do_removal(ctx, 100, lambda e: text in e.content)

    @purge.command(name='bot', aliases=['bots'])
    @commands.has_permissions(manage_messages=True)
    async def purge_bots(self, ctx : MyContext, prefix : Optional[str] = None, search : int = 25):
        """Remove a bot's user messages and messages with their optional prefix."""

        def predicate(msg):
            return (msg.webhook_id is None and msg.author.bot) or (prefix and msg.content.startswith(prefix))

        await self.do_removal(ctx, search, predicate)

    @purge.command(name='emoji', aliases=['emojis'])
    @commands.has_permissions(manage_messages=True)
    async def purge_emojis(self, ctx : MyContext, search : int):
        """Remove all messages containing a custom emoji."""

        custom_emoji = re.compile(r'<a?:[a-zA-Z0-9_]+:([0-9]+)>')

        def predicate(m):
            return custom_emoji.search(m.content)

        await self.do_removal(ctx, search, predicate)

    @purge.command(name='reactions')
    @commands.has_permissions(manage_messages=True)
    async def purge_reactions(self, ctx : MyContext, search : int):
        """Remove all reactions from messages that have them."""

        async with ctx.typing():
            if search > 2000:
                return await ctx.send(f'Too many messages to search. ({search}/2000)')
            
            total_reactions = 0
            async for message in ctx.history(limit=search, before=ctx.message):
                if len(message.reactions):
                    total_reactions += sum(r.count for r in message.reactions)
                    await message.clear_reactions()
                    await asyncio.sleep(.5)

            await ctx.send(f'Successfully removed {total_reactions} reactions.')

    @purge.command(name='threads')
    @commands.has_permissions(manage_messages=True)
    async def purge_threads(self, ctx : MyContext, search : int):
        """Remove threads from the channel."""

        async with ctx.typing():
            if search > 2000:
                return await ctx.send(f'Too many messages to search given ({search}/2000)')

            def check(m: discord.Message):
                return m.flags.has_thread

            deleted = await ctx.channel.purge(limit=search, check=check)
            thread_ids = [m.id for m in deleted]
            if not thread_ids:
                return await ctx.send("No threads found!")

            for thread_id in thread_ids:
                thread = self.bot.get_channel(thread_id)
                if isinstance(thread, discord.Thread):
                    await thread.delete()
                    await asyncio.sleep(0.5)

            spammers = Counter(m.author.display_name for m in deleted)
            deleted = len(deleted)
            messages = [f'{deleted} message'
                        f'{" and its associated thread was" if deleted == 1 else "s and their associated messages were"} '
                        f'removed.']

            if deleted:
                messages.append('')
                spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
                messages.extend(f'**{name}**: {count}' for name, count in spammers)

            to_send = '\n'.join(messages)

            if len(to_send) > 2000:
                await ctx.send(f'Successfully removed {deleted} messages and their associated threads.',
                               delete_after=1)
            else:
                await ctx.send(to_send, delete_after=10)


    @purge.command(name='custom')
    @commands.has_permissions(manage_messages=True)
    async def purge_custom(self, ctx : MyContext, *, args : str = None):
        """
        A more advanced purge command with a command-line-like syntax.

        Most options support multiple values to indicate 'any' match.
        If the value has spaces it must be quoted.
        The messages are only deleted if all options are met unless
        the `--or` flag is passed, in which case only if any is met.

        The following options are valid.
        `--user`: A mention or name of the user to remove.
        `--contains`: A substring to search for in the message.
        `--starts`: A substring to search if the message starts with.
        `--ends`: A substring to search if the message ends with.
        `--search`: Messages to search. Default 100. Max 2000.
        `--after`: Messages after this message ID.
        `--before`: Messages before this message ID.

        Flag options (no arguments):
        `--bot`: Check if it's a bot user.
        `--embeds`: Checks for embeds.
        `--files`: Checks for attachments.
        `--emoji`: Checks for custom emoji.
        `--reactions`: Checks for reactions.
        `--or`: Use logical OR for ALL options.
        `--not`: Use logical NOT for ALL options.   
        """
        if args is None:
            return await ctx.help()

        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument('--user', nargs='+')
        parser.add_argument('--contains', nargs='+')
        parser.add_argument('--starts', nargs='+')
        parser.add_argument('--ends', nargs='+')
        parser.add_argument('--or', action='store_true', dest='_or')
        parser.add_argument('--not', action='store_true', dest='_not')
        parser.add_argument('--emoji', action='store_true')
        parser.add_argument('--bot', action='store_const', const=lambda m: m.author.bot)
        parser.add_argument('--embeds', action='store_const', const=lambda m: len(m.embeds))
        parser.add_argument('--files', action='store_const', const=lambda m: len(m.attachments))
        parser.add_argument('--reactions', action='store_const', const=lambda m: len(m.reactions))
        parser.add_argument('--search', type=int)
        parser.add_argument('--after', type=int)
        parser.add_argument('--before', type=int)

        try:
            args = parser.parse_args(shlex.split(args))
        except Exception as e:
            await ctx.send(str(e))
            return

        predicates = []
        if args.bot:
            predicates.append(args.bot)

        if args.embeds:
            predicates.append(args.embeds)

        if args.files:
            predicates.append(args.files)

        if args.reactions:
            predicates.append(args.reactions)

        if args.emoji:
            custom_emoji = re.compile(r'<:(\w+):(\d+)>')
            predicates.append(lambda m: custom_emoji.search(m.content))

        if args.user:
            users = []
            converter = commands.MemberConverter()
            for u in args.user:
                try:
                    user = await converter.convert(ctx, u)
                    users.append(user)
                except Exception as e:
                    await ctx.send(str(e))
                    return

            predicates.append(lambda m: m.author in users)

        if args.contains:
            predicates.append(lambda m: any(sub in m.content for sub in args.contains))

        if args.starts:
            predicates.append(lambda m: any(m.content.startswith(s) for s in args.starts))

        if args.ends:
            predicates.append(lambda m: any(m.content.endswith(s) for s in args.ends))

        op = all if not args._or else any

        def predicate(m):
            r = op(p(m) for p in predicates)
            if args._not:
                return not r
            return r

        if args.after:
            if args.search is None:
                args.search = 2000

        if args.search is None:
            args.search = 100

        args.search = max(0, min(2000, args.search))  # clamp from 0-2000
        await self.do_removal(ctx, args.search, predicate, before=args.before, after=args.after)

        


def setup(bot):
    bot.add_cog(server(bot))