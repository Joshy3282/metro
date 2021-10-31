import discord
from discord.ext import commands


from utils.context import MyContext
from utils.converters import BotUser
from utils.useful import Embed


import datetime
import asyncio

SUPPORT_GUILD = 812143286457729055

def in_support():
    def predicate(ctx):
        return ctx.guild.id == SUPPORT_GUILD
    return commands.check(predicate)

def is_tester():
    def predicate(ctx):
        try:
            role = ctx.guild.get_role(861141649265262592)
        except:
            raise commands.BadArgument(f"You must have the tester role to use this command.\nJoin my support server (run `{ctx.prefix}support`) and type !tester for this to work.")
        if role in ctx.author.roles:
            return True
        else:
            raise commands.BadArgument(f'You must have the tester role to use this command.\nType `!tester` to get the role.')

    return commands.check(predicate)
        

class RoleView(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Metro Updates', style=discord.ButtonStyle.blurple, row=0, custom_id='metro_updates_button')
    async def metro_updates_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        
        guild = self.bot.get_guild(812143286457729055)

        role = guild.get_role(828795116000378931)
        if role in interaction.user.roles:
            
            embed = Embed()
            embed.description = 'Removed **Metro Updates** from your roles.'
            embed.color = discord.Colour.red()
            await interaction.user.remove_roles(role)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        else:

            embed = Embed()
            embed.description = 'Added **Metro Updates** to your roles.'
            embed.color = discord.Colour.green()
            await interaction.user.add_roles(role)
            return await interaction.response.send_message(embed=embed, ephemeral=True)



    @discord.ui.button(label='Server Annoucements', style=discord.ButtonStyle.blurple, row=1, custom_id='server_annoucements_button')
    async def server_annoucements_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        
        guild = self.bot.get_guild(812143286457729055)

        role = guild.get_role(828795624945614858)
        if role in interaction.user.roles:
            
            embed = Embed()
            embed.description = 'Removed **Server Annoucements** from your roles.'
            embed.color = discord.Colour.red()
            await interaction.user.remove_roles(role)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        else:

            embed = Embed()
            embed.description = 'Added **Server Annoucements** to your roles.'
            embed.color = discord.Colour.green()
            await interaction.user.add_roles(role)
            return await interaction.response.send_message(embed=embed, ephemeral=True)


class TesterButton(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Tester', style=discord.ButtonStyle.blurple, custom_id='metro_tester')
    async def tester_button(self, button : discord.ui.Button, interaction : discord.Interaction):

        guild = self.bot.get_guild(812143286457729055)

        role = guild.get_role(861141649265262592)
        if role in interaction.user.roles:

            embed = Embed()
            embed.description = 'Removed **Tester** from your roles.'
            embed.color = discord.Colour.red()
            await interaction.user.remove_roles(role)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            embed = Embed()
            embed.description = 'Added **Tester** to your roles.'
            embed.color = discord.Colour.green()
            await interaction.user.add_roles(role)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

            
class AllRoles(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Check my roles', style=discord.ButtonStyle.green, custom_id='all_roles')
    async def tester_button(self, button : discord.ui.Button, interaction : discord.Interaction):

        guild = self.bot.get_guild(812143286457729055)

        updates = guild.get_role(828795116000378931)
        annoucements = guild.get_role(828795624945614858)
        tester = guild.get_role(861141649265262592)

        if updates in interaction.user.roles:
            updates_y_n = self.bot.check
        else:
            updates_y_n = self.bot.cross

        if annoucements in interaction.user.roles:
            annouce_y_n = self.bot.check
        else:
            annouce_y_n = self.bot.cross

        if tester in interaction.user.roles:
            test_y_n = self.bot.check
        else:
            test_y_n = self.bot.cross


        embed = Embed()
        embed.title = 'Your Roles:'
        embed.description = f'**Metro Updates:** {updates_y_n} \n**Annoucements:** {annouce_y_n}\n\n**Tester:** {test_y_n}'
 
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Verify(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Verify', style=discord.ButtonStyle.green, custom_id='verify_button')
    async def verify_button(self, button : discord.ui.Button, interaction : discord.Interaction):
        

        await interaction.response.send_message(f'{self.bot.check} Verifying...',ephemeral=True)
        await asyncio.sleep(1.5)
        if interaction.user.created_at > (discord.utils.utcnow() - datetime.timedelta(days=3)):
            
            await interaction.user.send(f'You were kicked for being too new! (Account was created in the last 3 days)')
            await interaction.user.kick(reason='Kicked for being too new! (Account was created in the last 3 days)')

        else:
            
            role = discord.Object(id=902693712688197642)
            await interaction.user.remove_roles(role)

            await interaction.user.send(f'{self.bot.check} You were verified in Metro Support Server!')
            


        


class support(commands.Cog, description=':test_tube: Support only commands.'):
    def __init__(self, bot):
        self.bot = bot





    @commands.command(hidden=True)
    @commands.is_owner()
    async def support_roles(self, ctx : MyContext):

        if ctx.author.id != self.bot.owner_id:
            return 

        await ctx.message.delete()

        roles_channel = self.bot.get_channel(828466726659948576)

        embed = Embed()
        embed.title = 'Self-Roles'
        embed.description = 'Click on a button to add/remove that role.'

        tester_embed = Embed()
        tester_embed.title = 'Self-Roles'
        tester_embed.description = 'Click on a button to add/remove that role.'

        view = RoleView(ctx.bot)
        tester_view = TesterButton(ctx.bot)
        all_roles = AllRoles(ctx.bot)

        roles = Embed()
        roles.title='Check your roles'
        roles.description = 'Click below to see the roles you have'

        await roles_channel.send(embed=embed, view=view)
        await roles_channel.send(embed=tester_embed, view=tester_view)
        await roles_channel.send(embed=roles, view=all_roles)

        verify_channel = self.bot.get_channel(902694707161870376)

        verify_em = Embed()
        verify_em.title = 'Welcome to Metro Support Server!'
        verify_em.description = "Please click the **Verify** button below to gain access to the server. This checks your account creation date to detect spam. If you have any issues/questions please contact a support member."
        await verify_channel.send(embed=verify_em, view=Verify(ctx.bot))


    @commands.command()
    @in_support()
    async def addbot(
        self, 
        ctx : MyContext,
        user : BotUser,
        *,
        reason : str 
    ):
        """Request to add your bot to the server.
        
        To make a request you need your bot's user ID and a reason
        """

        confirm = await ctx.confirm(
            'This server\'s moderators have the right to kick or reject your bot for any reason.'
            '\nYou also agree that your bot does not have the following prefixes: `?`,`!`'
            '\nYour bot cannot have an avatar that might be considered NSFW, ping users when they join, post NSFW messages in not NSFW marked channels.'
            '\nRules that may apply to users should also be applied to bots.'
            '\n\nHit the **Confirm** button below to submit your request and agree to these terms.', timeout=60  
            )

        if confirm is False:
            return await ctx.send('Canceled.')
        if confirm is None:
            return await ctx.send('Timed out.')

        else:
            url = f'https://discord.com/oauth2/authorize?client_id={user.id}&scope=bot&guild_id={ctx.guild.id}'
            description = f"{reason}\n\n[Invite URL]({url})"

            embed = Embed(title='Bot Request',description=description)
            embed.add_field(name='Author',value=f'{ctx.author} (ID: {ctx.author.id})',inline=False)
            embed.add_field(name='Bot',value=f'{user} (ID: {user.id})',inline=False)
            embed.timestamp = ctx.message.created_at

            embed.set_author(name=user.id, icon_url=user.display_avatar.url)
            embed.set_footer(text=ctx.author.id)

            try:
                channel = self.bot.get_channel(904184918840602684)
                message = await channel.send(embed=embed)
            except discord.HTTPException as e:
                return await ctx.send(f'Failed to add your bot.\n{str(e)}')

            await message.add_reaction(self.bot.check)
            await message.add_reaction(self.bot.cross)

            await ctx.send('Your bot request has been submitted to the moderators. I will DM you about the status of your request.')


    
def setup(bot):
    bot.add_cog(support(bot))
