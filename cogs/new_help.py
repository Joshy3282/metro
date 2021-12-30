from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from discord.ext import commands
import utils
import itertools
import discord


class PaginatorButton(discord.ui.Button["Paginator"]):
  def __init__(self, *, emoji: Optional[Union[discord.PartialEmoji, str]] = None, label: Optional[str] = None, style: discord.ButtonStyle = discord.ButtonStyle.blurple, position: Optional[int] = None,) -> None:
       
        super().__init__(emoji=emoji, label=label, style=style)

        
        if not emoji and not label:
            raise ValueError("A label or emoji must be provided.")

        
        self.position: Optional[int] = position

    
  async def callback(self, interaction: discord.Interaction):
        
        assert self.view is not None

        
        if self.custom_id == "stop_button":
            await self.view.stop()
            return

        
        if self.custom_id == "right_button":
            self.view.current_page += 1
        elif self.custom_id == "left_button":
            self.view.current_page -= 1
        elif self.custom_id == "first_button":
            self.view.current_page = 0
        elif self.custom_id == "last_button":
            self.view.current_page = self.view.max_pages - 1

       
        self.view.page_string = f"Page {self.view.current_page + 1}/{self.view.max_pages}"
        
        if self.view.PAGE_BUTTON is not None:
            self.view.PAGE_BUTTON.label = self.view.page_string

        
        if self.view.current_page == 0:
            if self.view.FIRST_BUTTON is not None:
                self.view.FIRST_BUTTON.disabled = True
            if self.view.LEFT_BUTTON is not None:
                self.view.LEFT_BUTTON.disabled = True
        else:
            if self.view.FIRST_BUTTON is not None:
                self.view.FIRST_BUTTON.disabled = False
            if self.view.LEFT_BUTTON is not None:
                self.view.LEFT_BUTTON.disabled = False

        if self.view.current_page >= self.view.max_pages - 1:
            if self.view.LAST_BUTTON is not None:
                self.view.LAST_BUTTON.disabled = True
            if self.view.RIGHT_BUTTON is not None:
                self.view.RIGHT_BUTTON.disabled = True
        else:
            if self.view.LAST_BUTTON is not None:
                self.view.LAST_BUTTON.disabled = False
            if self.view.RIGHT_BUTTON is not None:
                self.view.RIGHT_BUTTON.disabled = False

        
        page_kwargs, _ = await self.view.get_page_kwargs(self.view.current_page)
        assert interaction.message is not None and self.view.message is not None

        
        try:
            await interaction.message.edit(**page_kwargs)
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            await self.view.message.edit(**page_kwargs)

class Paginator(discord.ui.View):
   
    FIRST_BUTTON: PaginatorButton
    LAST_BUTTON: PaginatorButton
    LEFT_BUTTON: PaginatorButton
    RIGHT_BUTTON: PaginatorButton
    STOP_BUTTON: PaginatorButton
    PAGE_BUTTON: PaginatorButton

    def __init__(
        self,
        pages: Union[List[discord.Embed], List[str]],
        ctx: Optional[commands.Context] = None,
        author_id: Optional[int] = None,
        *,
        buttons: Dict[str, Union[PaginatorButton, None]] = {},
        disable_after: bool = False,
        delete_message_after: bool = False,
        clear_after: bool = False,
        timeout: int = 180,
    ):
        
        super().__init__(timeout=timeout)

       
        DEFAULT_BUTTONS: Dict[str, Union[PaginatorButton, None]] = {
            "first": PaginatorButton(emoji = "⏮️", style=discord.ButtonStyle.secondary),
            "left": PaginatorButton(emoji="◀️", style=discord.ButtonStyle.secondary),
            "right": PaginatorButton(emoji="▶️", style=discord.ButtonStyle.secondary),
            "last": PaginatorButton(emoji="⏭️", style=discord.ButtonStyle.secondary),
            "stop": PaginatorButton(emoji="⏹️", style=discord.ButtonStyle.secondary),
            "page": None
        }

        self.ctx: Optional[commands.Context] = ctx
        self.author_id: Optional[int] = author_id

        self._disable_after = disable_after
        self._delete_message_after = delete_message_after
        self._clear_after = clear_after
        self.buttons: Dict[str, Union[PaginatorButton, None]] = buttons or DEFAULT_BUTTONS
        self.message: Optional[discord.Message] = None

        
        self.pages: Union[List[discord.Embed], List[str]] = pages
        self.current_page: int = 0
        self.max_pages: int = len(self.pages)
        self.page_string: str = f"Page {self.current_page + 1}/{self.max_pages}"

        self._add_buttons(DEFAULT_BUTTONS)

    
    def _add_buttons(self, default_buttons: Dict[str, Union[PaginatorButton, None]]) -> None:
        
        if self.max_pages <= 1:
            super().stop()
            return

        
        VALID_KEYS = ["first", "left", "right", "last", "stop", "page"]
        if all(b in VALID_KEYS for b in self.buttons.keys()) is False:
            raise ValueError(f"Buttons keys must be in: `{', '.join(VALID_KEYS)}`")

        if all(isinstance(b, PaginatorButton) or b is None for b in self.buttons.values()) is False:
            raise ValueError("Buttons values must be PaginatorButton instances or None.")

        
        button: Union[PaginatorButton, None]

       
        for name, button in default_buttons.items():
            
            for custom_name, custom_button in self.buttons.items():
               
                if name == custom_name:
                    button = custom_button

           
            setattr(self, f"{name}_button".upper(), button)

            
            if button is None:
                continue

            
            button.custom_id = f"{name}_button"

           
            if button.custom_id == "page_button":
                button.label = self.page_string
                button.disabled = True

           
            if button.custom_id in ("first_button", "last_button") and self.max_pages <= 2:
                continue

            
            if button.custom_id in ("first_button", "left_button") and self.current_page <= 0:
                button.disabled = True

           
            if button.custom_id in ("last_button", "right_button") and self.current_page >= self.max_pages - 1:
                button.disabled = True

           
            self.add_item(button)

        
        self._set_button_positions()

    
    def _set_button_positions(self) -> None:
        """Moves the buttons to the desired position"""

        button: PaginatorButton

        
        for button in self.children:
           
            if button.position is not None:
              
                self.children.insert(button.position, self.children.pop(self.children.index(button)))

   
    async def format_page(self, page: Union[discord.Embed, str]) -> Union[discord.Embed, str]:
        return page

    
    async def get_page_kwargs(
        self: "Paginator", page: int, send_kwargs: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[Literal["content", "embed", "view"], Union[discord.Embed, str, "Paginator", None]], Dict[str, Any]]:

        if send_kwargs is not None:
           
            send_kwargs.pop("content", None)
            send_kwargs.pop("embed", None)
            send_kwargs.pop("embeds", None)

       
        formatted_page: Union[str, discord.Embed, None] = await discord.utils.maybe_coroutine(self.format_page, self.pages[page]) 
        if isinstance(formatted_page, str):
           
            formatted_page += f"\n\n{self.page_string}"
            return {"content": formatted_page, "embed": None, "view": self}, send_kwargs or {}

       
        elif isinstance(formatted_page, discord.Embed):
            if formatted_page.footer.text is not discord.Embed.Empty:
              formatted_page.set_footer(text=f"{formatted_page.footer.text} - {self.page_string}")
              
            else:
              formatted_page.set_footer(text=self.page_string)
            return {"content": None, "embed": formatted_page, "view": self}, send_kwargs or {}

        
        else:
            return {}, send_kwargs or {}

    
    async def on_timeout(self) -> None:
        await self.stop()

   
    async def interaction_check(self, interaction: discord.Interaction):
        
        if not interaction.user or not self.ctx or not self.author_id:
            return True

       
        if self.author_id and not self.ctx:
            return interaction.user.id == self.author_id
        else:
            
            if not interaction.user.id in {
                getattr(self.ctx.bot, "owner_id", None),
                self.ctx.author.id,
                *getattr(self.ctx.bot, "owner_ids", {}),
            }:
                return False

        
        return True

   
    async def stop(self):
        
        super().stop()

        assert self.message is not None

        

        if self._delete_message_after:
            await self.message.delete()
            return

        elif self._clear_after:
            await self.message.edit(view=None)
            return

        elif self._disable_after:
            
            for item in self.children:
                item.disabled = True

            
            await self.message.edit(view=self)

    
    async def send_as_interaction(
        self, interaction: discord.Interaction, ephemeral: bool = False, *args, **kwargs
    ) -> Optional[Union[discord.Message, discord.WebhookMessage]]:
        page_kwargs, send_kwargs = await self.get_page_kwargs(self.current_page, kwargs)
        if not interaction.response.is_done():
            send = interaction.response.send_message
        else:
            
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=ephemeral)

            send_kwargs["wait"] = True
            send = interaction.followup.send

        ret = await send(*args, ephemeral=ephemeral, **page_kwargs, **send_kwargs)

        if not ret:
            try:
                self.message = await interaction.original_message()
            except (discord.ClientException, discord.HTTPException):
                self.message = None
        else:
            self.message = ret

        return self.message

   
    async def send(
        self, send_to: Union[discord.abc.Messageable, discord.Message], *args: Any, **kwargs: Any
    ) -> discord.Message:

        
        page_kwargs, send_kwargs = await self.get_page_kwargs(self.current_page, kwargs)

        if isinstance(send_to, discord.Message):
           
            self.message = await send_to.reply(*args, **page_kwargs, **send_kwargs)
        else:
           
            self.message = await send_to.send(*args, **page_kwargs, **send_kwargs)

        
        return self.message

class SendHelp(Paginator):
  async def format_page(self, item): 
    emby = discord.Embed(description = item, color = 15428885)
    return emby

class Help(commands.MinimalHelpCommand):
  async def send_pages(self):
    menu = SendHelp(self.paginator.pages, ctx = self.context, delete_message_after = True)

    await menu.send(self.context.channel)

  def add_command_formatting(self, command):
        """A utility function to format commands and groups.
        Parameters
        ------------
        command: :class:`Command`
            The command to format.
        """

        if command.description:
            self.paginator.add_line(command.description, empty=True)

        signature = self.get_command_signature(command)
        if command.aliases:
            self.paginator.add_line(signature)
            self.add_aliases_formatting(command.aliases)
        else:
            self.paginator.add_line(discord.utils.escape_markdown(signature), empty=True)


        if command.help:
            try:
                self.paginator.add_line(command.help, empty=True)
            except RuntimeError:
                for line in command.help.splitlines():
                    self.paginator.add_line(line)
                self.paginator.add_line()

  def add_subcommand_formatting(self, command):
        if len(command.name) < 15:
            empty_space = 15 - len(command.name)
            signature = f"`{command.name}{' '*empty_space}:` {command.short_doc if len(command.short_doc) < 58 else f'{command.short_doc[0:58]}...'}"
        else:
            signature = f"`{command.name[0:14]}...` {command.short_doc if len(command.short_doc) < 58 else f'{command.short_doc[0:58]}...'}"
        self.paginator.add_line(signature)
        #fmt = "{0}{1} \N{EN DASH} {2}" if command.short_doc else "{0}{1}"
        #self.paginator.add_line(fmt.format(discord.utils.escape_markdown(self.context.clean_prefix), discord.utils.escape_markdown(command.qualified_name), command.short_doc))

  async def send_group_help(self, group):
    self.add_command_formatting(group)

    filtered = await self.filter_commands(group.commands, sort=self.sort_commands)
    if filtered:
        note = self.get_opening_note()

        if note:
            self.paginator.add_line(note, empty=True)

        self.paginator.add_line('**%s**' % self.commands_heading)
        for command in filtered:
            self.add_subcommand_formatting(command)

        note = self.get_ending_note()
        if note:
            self.paginator.add_line()
            self.paginator.add_line(note)

    await self.send_pages()
        
  async def send_bot_help(self, mapping):
    ctx = self.context
    bot = ctx.bot

    if bot.description:
      self.paginator.add_line(bot.description, empty = True)

    note = self.get_opening_note()

    if note:
      self.paginator.add_line(note, empty=True)

    no_category = f'\u200b{self.no_category}'

    def get_category(command, *, no_category=no_category):
      cog = command.cog
      return f"__**{cog.qualified_name}:**__ \n{cog.description}" if cog is not None else no_category

    filtered = await self.filter_commands(bot.commands, sort = True, key=get_category)
    to_iterate = itertools.groupby(filtered, key=get_category)

    for category, Commands in to_iterate:
      self.paginator.add_line(category)

    note = self.get_ending_note()
    if note:
      self.paginator.add_line()
      self.paginator.add_line(note)

    await self.send_pages()

class newhelp(commands.Cog, description='newhelpcommandcog'):
    def __init__(self, bot):
        
        attrs = {
            'name' : 'jd_help',
            'description' : 'Show bot help or help for a command',
            'slash_command' : True,
            'message_command' : True,
            'extras' : {'examples' : "[p]jd_help ban\n[p]jd_help config enable\n[p]jd_help invite"}
        }
        self.bot = bot
        bot.new_help = Help(command_attrs=attrs)

    @property
    def emoji(self) -> str:
        return 'ℹ️'

    @commands.command()
    async def tests(self, ctx):
        pass

def setup(bot):
    bot.add_cog(newhelp(bot))