import asyncio
import discord
from discord.ext import commands, menus

from typing import Any, List, Optional, Union

from discord.ext.commands.core import Command, Group
from discord.ext.commands.errors import CommandError, CommandInvokeError

from utils.new_pages import SimplePageSource, SimplePages

import functools

class ConfirmationView(discord.ui.View):
    def __init__(self, *, timeout: float, author_id: int, ctx, delete_after: bool) -> None:
        super().__init__(timeout=timeout)
        self.value: Optional[bool] = None
        self.delete_after: bool = delete_after
        self.author_id: int = author_id
        self.ctx = ctx
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.author_id:
            return True
        else:
            await interaction.response.send_message('This confirmation dialog is not for you.', ephemeral=True)
            return False

    async def on_timeout(self) -> None:
        self.confirm.disabled = True
        self.cancel.disabled = True
        self.value = None
        if self.message:
            await self.message.edit(view=self)

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        await interaction.response.defer()
        if self.delete_after:
            await interaction.delete_original_message()
        self.stop()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        await interaction.response.defer()
        if self.delete_after:
            await interaction.delete_original_message()
        self.stop()



class MyContext(commands.Context):

    async def check(self):
        emoji = self.bot.get_emoji(819254444197019669)

        try:
            await self.message.add_reaction(emoji)
        except discord.HTTPException:
            pass
               

    async def cross(self):
        emoji = self.bot.get_emoji(819254444217860116)

        try:
            await self.message.add_reaction(emoji)
        except discord.HTTPException:
            pass

    #async def defer(self, hide : bool = True, trigger_typing : bool = True):
        #await super().defer(ephemeral=hide, trigger_typing=trigger_typing)

    async def send(self, content : str = None, embed : discord.Embed = None, hide : bool = False, reply: bool = True, reference: Any = None, **kwargs):

        if content: 
            content=str(content)

            if self.bot.http.token in content:
                content = content.replace(self.bot.http.token, "[Token Hidden for privacy reasons]")

        if reply:
            reference = self.message
        message = await super().send(content=content, reference=reference, embed=embed, ephemeral=hide, **kwargs)


        return message
          

    async def confirm(
        self,
        message : str,
        *,
        timeout : float = 60.0,
        delete_after : bool = True,
        author_id : Optional[int] = None,
        interaction : Optional[discord.Interaction] = None

    ) -> Optional[bool]:

        author_id = author_id or self.author.id

        view = ConfirmationView(
            timeout=timeout,
            delete_after=delete_after,
            ctx=self,
            author_id=author_id

        )
        if interaction:
            view.message = await interaction.response.send_message(message, view=view)
            await view.wait()
            return view.value
        else:
            view.message = await self.send(message, view=view)
            await view.wait()
            return view.value
        

    async def paginate(
        self,
        entries : List,
        *,
        per_page : int = 8,
        source : Optional[menus.ListPageSource] = None,
        hide : bool = False,
        compact: bool = False

    ):

        default_source = SimplePageSource(
            entries=list(entries),
            per_page=per_page
        )
        source = source or default_source

        menu = SimplePages(
            source=source, ctx=self, hide=hide, compact=compact)
        await menu.start()

    @discord.utils.cached_property
    def replied_reference(self):
        ref = self.message.reference
        if ref and isinstance(ref.resolved, discord.Message):
            return ref.resolved.to_reference()
        return None

    
    async def help(self):
        await self.send_help(self.command)

    async def get_message(self, id : int, channel : Optional[discord.TextChannel] = None):
        channel = channel or self.channel

        message = discord.utils.get(self.bot.cached_messages, id=id)
        if message:
            return message
        else:
            if channel:
                return await channel.fetch_message(id)
            else:
                return None

    async def emojify(self, object, custom_emojis : bool = True):
        if bool(object) is True:
            if custom_emojis is True:
                return self.bot.check
            else:
                return '✅'
        if bool(object) is False:
            if custom_emojis is True:
                return self.bot.cross
            else:
                return '❌'

    async def ghost_ping(self, member: Union[discord.User, discord.Member], message: Optional[str] = None, *, channel: Optional[discord.TextChannel] = None):
        channel = channel or self.channel
        await channel.send(f"{member.mention} {message if message else ''}", delete_after=0.1)

    async def get_help(self, command: commands.Command) -> discord.Embed:
        help_command = self.bot.help_command

        cmd = help_command.copy()
        cmd.context = self

        try:
            if hasattr(command, "__cog_commands__"):
                return await cmd.send_cog_help(command)
            elif isinstance(command, Group):
                return await cmd.send_group_help(command)
            elif isinstance(command, Command):
                return await cmd.get_command_help(command)
        except CommandError as e:
            await cmd.on_help_command_error(self, e)
    
    @property
    def color(self):
        return self.me.color if self.me.color not in (discord.Color.default(), discord.Embed.Empty, None)\
            else discord.Color.blue()

    @property
    def colour(self):
        return self.color