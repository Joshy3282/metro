import datetime
import json
from typing import Optional, Union
import discord
import re
import pytz
import unicodedata
import unidecode
import stringcase
from discord.ext import commands

from bot import MetroBot
from utils.checks import can_execute_action
from utils.converters import ActionReason, RoleConverter
from utils.custom_context import MyContext
from utils.remind_utils import FutureTime, UserFriendlyTime, human_timedelta
from utils.useful import Cooldown, Embed
from utils.parsing import RoleParser
from cogs.utility import Timer


# Parts of lockdown I took from Hecate thx
# https://github.com/Hecate946/Neutra/blob/main/cogs/mod.py#L365-L477
# not really but i took ideas from it

# role is mainly from phencogs rewritten for 2.0
# https://github.com/phenom4n4n/phen-cogs/blob/master/roleutils/roles.py
# for redbot btw so you might need to make adjustments

def setup(bot: MetroBot):
    bot.add_cog(serverutils(bot))

class serverutils(commands.Cog, description='Server utilities like role, lockdown, nicknames.'):
    def __init__(self, bot: MetroBot):
        self.bot = bot

    @property
    def emoji(self) -> str:
        return '📓'

    @commands.command(name="lockdown", brief="Lockdown a channel.", aliases=["lock"])
    @commands.has_permissions(send_messages=True, manage_channels=True)
    @commands.bot_has_permissions(send_messages=True, manage_channels=True)
    async def lockdown_cmd(
            self, ctx : MyContext,
            channel : Optional[discord.TextChannel] = None, *,
            duration : UserFriendlyTime(commands.clean_content, default='\u2026') = None):
        """
        Locks down a channel by changing permissions for the default role.
        This will not work if your server is set up improperly.
        """
        channel = channel or ctx.channel
        await ctx.trigger_typing()

        if not channel.permissions_for(ctx.guild.me).read_messages:
            raise commands.BadArgument(
                f"I need to be able to read messages in {channel.mention}"
            )
        if not channel.permissions_for(ctx.guild.me).send_messages:
            raise commands.BadArgument(
                f"I need to be able to send messages in {channel.mention}"
            )

        query = """
                SELECT (id)
                FROM reminders
                WHERE event = 'lockdown'
                AND EXTRA->'kwargs'->>'channel_id' = $1; 
                """
        data = await self.bot.db.fetchval(query, str(channel.id))
        if data:
            raise commands.BadArgument(f"{self.bot.cross} Channel {channel.mention} is already locked.")
        
        overwrites = channel.overwrites_for(ctx.guild.default_role)
        perms = overwrites.send_messages
        if perms is False:
            raise commands.BadArgument(f"{self.bot.cross} Channel {channel.mention} is already locked.")

        reminder_cog = self.bot.get_cog('utility')
        if not reminder_cog:
            raise commands.BadArgument(f'This feature is currently unavailable.')

        message = await ctx.send(f'Locking {channel.mention} ...')
        bot_perms = channel.overwrites_for(ctx.guild.me)
        if not bot_perms.send_messages:
            bot_perms.send_messages = True
            await channel.set_permissions(
                ctx.guild.me, overwrite=bot_perms, reason="For channel lockdown."
            )

        endtime = duration.dt.replace(tzinfo=None) if duration and duration.dt else None

        if endtime:
            await reminder_cog.create_timer(
                endtime,
                "lockdown",
                ctx.guild.id,
                ctx.author.id,
                ctx.channel.id,
                perms=perms,
                channel_id=channel.id,
                connection=self.bot.db,
                created=ctx.message.created_at.replace(tzinfo=None)
            )
        overwrites.send_messages = False
        reason = "Channel locked by command."
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=await ActionReason().convert(ctx, reason),
        )

        if duration and duration.dt:
            timefmt = human_timedelta(endtime - datetime.timedelta(seconds=2))
        else:
            timefmt = None
        
        ft = f" for {timefmt}" if timefmt else ""
        await message.edit(content=f'{self.bot.check} Channel {channel.mention} locked{ft}')
        
    @commands.command(name="unlockdown", brief="Unlock a channel.", aliases=["unlock"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(send_messages=True, manage_channels=True)
    async def unlockdown_cmd(self,
                           ctx : MyContext,
                           channel: discord.TextChannel = None):
        """
        Unlocks down a channel by changing permissions for the default role.
        This will not work if your server is set up improperly
        """

        channel = channel or ctx.channel

        await ctx.trigger_typing()
        if not channel.permissions_for(ctx.guild.me).read_messages:
            raise commands.BadArgument(
                f"I need to be able to read messages in {channel.mention}"
            )
        if not channel.permissions_for(ctx.guild.me).send_messages:
            raise commands.BadArgument(
                f"I need to be able to send messages in {channel.mention}"
            )

        query = """
                SELECT (id, extra)
                FROM reminders
                WHERE event = 'lockdown'
                AND extra->'kwargs'->>'channel_id' = $1;
                """
        s = await self.bot.db.fetchval(query, str(channel.id))
        if not s:
            overwrites = channel.overwrites_for(ctx.guild.default_role)
            perms = overwrites.send_messages
            if perms is True:
                return await ctx.send(f"Channel {channel.mention} is already unlocked.")
            else:
                pass   
        else:
            pass
           
        message = await ctx.send(f"Unlocking {channel.mention} ...")
        if s:
            task_id = s[0]
            args_and_kwargs = json.loads(s[1])
            perms = args_and_kwargs["kwargs"]["perms"]
            

            query = """
                    DELETE FROM reminders
                    WHERE id = $1
                    """
            await self.bot.db.execute(query, task_id)
        reason = "Channel unlocked by command execution."

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=await ActionReason().convert(ctx, reason),
        )
        await message.edit(
            content=f"{self.bot.check} Channel {channel.mention} unlocked."
        )
    

    async def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    async def show_roleinfo(self, role: discord.Role):
        if role.guild.chunked is False:
            await role.guild.chunk()

        desc = [
            role.mention,
            f"Member: {len(role.members)} | Position: {role.position}",
            f"Colour: {role.colour}",
            f"Hoisted: {role.hoist}",
            f"Mentionable: {role.mentionable}"
        ]
        if role.managed:
            desc.append(f"Managed: {role.managed}")
        
        embed = Embed()
        embed.colour = role.colour
        embed.title = role.name
        embed.description = "\n".join(desc)
        embed.timestamp = role.created_at
        embed.set_footer(text=f"ID: {role.id}")

        return embed
        
    @commands.group(invoke_without_command=True)
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def role(self, ctx: MyContext, member : discord.Member, *, role : RoleConverter):
        """
        Base command for modifying roles.
        
        Invoking this command without subcommands will add or remove the given role from the member, 
        depending on whether they already had it.
        """
        if not can_execute_action(ctx, ctx.author, member):
            return await ctx.send('You are not high enough in role hierarchy to edit roles from this member.')

        if role in member.roles:
            await ctx.invoke(self.role_remove, member=member, role=role)
            return
        elif role not in member.roles:
            await ctx.invoke(self.role_add, member=member, role=role)
            return
        else:
            await ctx.help() 

    @role.error
    async def role_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send_help("role")


    @role.command(name='add')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def role_add(self, ctx : MyContext, member : discord.Member, *, role : RoleConverter):
        """Add a role to a member."""

        if role in member.roles:
            return await ctx.send(f"**{member}** already has that role. Try removing it instead.")

        if not can_execute_action(ctx, ctx.author, member):
            return await ctx.send('You are not high enough in role hierarchy to give roles to this member.')

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to add this role due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            return await ctx.send(to_send)

        try:
            await member.add_roles(role, reason=f'Role command invoked by: {ctx.author} (ID: {ctx.author.id})')
        except discord.HTTPException as e:
            return await ctx.send(f"Had trouble adding this role: {e}")
        await ctx.send(f"Added **{role.name}** to **{member}**")

        
    @role.command(name='remove')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def role_remove(self, ctx : MyContext, member : discord.Member, *, role : RoleConverter):
        """Remove a role from a member."""

        if not role in member.roles:
            return await ctx.send(f"**{member}** doesn't have that role. Try adding it instead.")

        if not can_execute_action(ctx, ctx.author, member):
            return await ctx.send('You are not high enough in role hierarchy to remove roles to this member.')

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to remove this role due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            return await ctx.send(to_send)

        try:
            await member.remove_roles(role, reason=f'Role command invoked by: {ctx.author} (ID: {ctx.author.id})')
        except discord.HTTPException as e:
            return await ctx.send(f"Had trouble removing this role: {e}")
        await ctx.send(f"Removed **{role.name}** from **{member}**")

    @role.command(name='addmulti')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 6, 1, 4, commands.BucketType.guild))
    async def role_addmulti(self, ctx: MyContext, role: RoleConverter, *members: discord.Member):
        """Add a role to multiple members."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to add this role due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            return await ctx.send(to_send)

        success, hierarchy, already_has = [], [], []
        for member in members:
            if not can_execute_action(ctx, ctx.author, member):
                hierarchy.append(str(member))
                continue

            if role not in member.roles:
                await member.add_roles(role, reason=f'Add-multi role command invoked by: {ctx.author} (ID: {ctx.author.id})')
                success.append(str(member))
            else:
                already_has.append(str(member))

        to_send = []
        if success:
            to_send.append(f"Added **{role.name}** to {', '.join(success)}")
        if already_has:
            to_send.append(f"{', '.join(already_has)} already had **{role.name}**")
        if hierarchy:
            to_send.append(f"You are not high enough in role hierarchy to add roles to: {', '.join(hierarchy)}")
        if to_send:
            await ctx.send("\n".join(to_send))


    @role.command(name='removemulti')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 6, 1, 4, commands.BucketType.guild))
    async def role_removemulti(self, ctx: MyContext, role : RoleConverter, *members: discord.Member):
        """Remove a role from multiple members."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to remove this role due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            return await ctx.send(to_send)

        success, hierarchy, already_has = [], [], []
        for member in members:
            if not can_execute_action(ctx, ctx.author, member):
                hierarchy.append(str(member))
                continue

            if role in member.roles:
                await member.remove_roles(role, reason=f'Remove-multi role command invoked by: {ctx.author} (ID: {ctx.author.id})')
                success.append(str(member))
            else:
                already_has.append(str(member))

        to_send = []
        if success:
            to_send.append(f"Removed **{role.name}** from {', '.join(success)}")
        if already_has:
            to_send.append(f"{', '.join(already_has)} doesn't have **{role.name}**")
        if hierarchy:
            to_send.append(f"You are not high enough in role hierarchy to remove roles from: {', '.join(hierarchy)}")
        if to_send:
            await ctx.send("\n".join(to_send))


    @role.command(name='all')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_all(self, ctx: MyContext, *, role: RoleConverter):
        """Add a role to all members of the guild."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to add roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to add **{role.name}** to **{ctx.guild.member_count}** members.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to add **{role.name}** to **{len(ctx.guild.members)}** members.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for member in ctx.guild.members:
                if not can_execute_action(ctx, ctx.author, member):
                    failed += 1
                    continue

                if role in member.roles:
                    already_has += 1
                    continue

                try:
                    await member.add_roles(role, reason=f'Role-all invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully added **{role.name}** to {success}/{len(ctx.guild.members)} members."
        if already_has:
            to_send += f"{already_has} members already had **{role.name}**"
        if failed:
            to_send += f"Failed to add **{role.name}** to {failed} members due to role hierarchy or permission errors."

        await ctx.send(to_send)

    @role.command(name='rall', aliases=['removeall'])
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_rall(self, ctx: MyContext, *, role: RoleConverter):
        """Remove a role from all members of the guild."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to remove roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}``"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to remove **{role.name}** from **{ctx.guild.member_count}** members.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to remove **{role.name}** from **{len(ctx.guild.members)}** members.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for member in ctx.guild.members:
                if not can_execute_action(ctx, ctx.author, member):
                    failed += 1
                    continue

                if not role in member.roles:
                    already_has += 1
                    continue

                try:
                    await member.remove_roles(role, reason=f'Role-removeall invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully removed **{role.name}** from {success}/{len(ctx.guild.members)} members."
        if already_has:
            to_send += f"{already_has} members didn't even have **{role.name}**"
        if failed:
            to_send += f"Failed to remove **{role.name}** from {failed} members due to role hierarchy or permission errors."

        await ctx.send(to_send)

    @role.command(name='bots')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_bots(self, ctx: MyContext, *, role: RoleConverter):
        """Add a role to all bots in the guild."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to add roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to add **{role.name}** to **{len(ctx.guild.bots)}** bots.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to add **{role.name}** to **{len(ctx.guild.bots)}** bots.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for bot in ctx.guild.bots:
                if not can_execute_action(ctx, ctx.author, bot):
                    failed += 1
                    continue

                if role in bot.roles:
                    already_has += 1
                    continue

                try:
                    await bot.add_roles(role, reason=f'Role-all-bots invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully added **{role.name}** to {success}/{len(ctx.guild.bots)} bots."
        if already_has:
            to_send += f"{already_has} bots already had **{role.name}**"
        if failed:
            to_send += f"Failed to add **{role.name}** to {failed} bots due to role hierarchy or permission errors."

        await ctx.send(to_send)

    @role.command(name='rbots')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_rbots(self, ctx: MyContext, *, role: RoleConverter):
        """Remove a role from all bots in the guild."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to remove roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}``"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to remove **{role.name}** from **{len(ctx.guild.bots)}** bots.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to remove **{role.name}** from **{len(ctx.guild.bots)}** bots.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for bot in ctx.guild.bots:
                if not can_execute_action(ctx, ctx.author, bot):
                    failed += 1
                    continue

                if not role in bot.roles:
                    already_has += 1
                    continue

                try:
                    await bot.remove_roles(role, reason=f'Role-removeall-bots invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully removed **{role.name}** from {success}/{len(ctx.guild.bots)} bots."
        if already_has:
            to_send += f"{already_has} bots didn't even have **{role.name}**"
        if failed:
            to_send += f"Failed to remove **{role.name}** to {failed} bots due to role hierarchy or permission errors."

        await ctx.send(to_send)

    @role.command(name='humans')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_humans(self, ctx: MyContext, *, role: RoleConverter):
        """Add a role to all humans in the guild."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to add roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to add **{role.name}** to **{len(ctx.guild.humans)}** humans.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to add **{role.name}** to **{len(ctx.guild.humans)}** humans.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for human in ctx.guild.humans:
                if not can_execute_action(ctx, ctx.author, human):
                    failed += 1
                    continue

                if role in human.roles:
                    already_has += 1
                    continue

                try:
                    await human.add_roles(role, reason=f'Role-all-humans invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully added **{role.name}** to {success}/{len(ctx.guild.humans)} humans."
        if already_has:
            to_send += f"{already_has} humans already had **{role.name}**"
        if failed:
            to_send += f"Failed to add **{role.name}** to {failed} humans due to role hierarchy or permission errors."

        await ctx.send(to_send)

    @role.command(name='rhumans')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_rhumans(self, ctx: MyContext, *, role: RoleConverter):
        """Remove a role from all humans in the guild."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to remove roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to remove **{role.name}** from **{len(ctx.guild.humans)}** humans.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to remove **{role.name}** from **{len(ctx.guild.humans)}** humans.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for human in ctx.guild.humans:
                if not can_execute_action(ctx, ctx.author, human):
                    failed += 1
                    continue

                if not role in human.roles:
                    already_has += 1
                    continue

                try:
                    await human.remove_roles(role, reason=f'Role-removeall-humans invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully removed **{role.name}** from {success}/{len(ctx.guild.humans)} humans."
        if already_has:
            to_send += f"{already_has} humans didn't even have **{role.name}**"
        if failed:
            to_send += f"Failed to remove **{role.name}** to {failed} humans due to role hierarchy or permission errors."

        await ctx.send(to_send)

    @role.command(
        name='list',
        extras= {
            "examples" : "[p]role list \n [p]role list Name: {role.name} - ID: {role.id} \n [p]role list Role created at: {role.created_at_timestamp}"
        }
    )
    @commands.bot_has_guild_permissions(embed_links=True)
    async def role_list(self, ctx: MyContext, *, tagscript : str = None) -> Embed:
        """
        List all the roles the guild has.
        
        The `tagscript` argument is the way you want to format the roles.
        [Any attribute](https://enhanced-dpy.readthedocs.io/en/latest/api.html#discord.Role) a role has, you can add there.
        """

        if not tagscript:
            e = Embed()
            e.colour = discord.Colour.yellow()
            e.description = "\n".join([f'{x.mention} - {x.id}' for x in ctx.guild.roles])
            e.set_footer(text=f'{len(ctx.guild.roles)} roles.')
            return await ctx.send(embed=e)
        else:
            tagscript = await self.cleanup_code(tagscript)
            to_append = []
            for role in ctx.guild.roles:
                r = RoleParser.parse(tagscript, {"role" : role})
                to_append.append(r)

            e = Embed()
            e.colour = discord.Colour.yellow()
            e.description = '\n'.join(to_append)

            await ctx.send(embed=e)
            

    @role.command(name='info')
    @commands.bot_has_guild_permissions(embed_links=True)
    async def role_info(self, ctx: MyContext, *, role: RoleConverter):
        """Show a role's information."""
        await ctx.send(embed=await self.show_roleinfo(role))


    @role.command(name='color')
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.has_guild_permissions(manage_roles=True)
    async def role_color(self, ctx: MyContext, role: RoleConverter, *, color: discord.Color):
        """Change a role's color."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to edit this role due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        await role.edit(color=color)
        await ctx.send(f"Changed **{role.name}**'s color to **{color}**", embed=await self.show_roleinfo(role))
    
    @role.command(name='hoist')
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.has_guild_permissions(manage_roles=True)
    async def role_hoist(self, ctx: MyContext, role: RoleConverter, hoisted: bool = None):
        """Toggle a role's hoist status."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to edit this role due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        hoisted = hoisted if hoisted is not None else not role.hoist

        await role.edit(hoist=hoisted)
        term = "now longer" if hoisted is False else "now"
        await ctx.send(f"**{role.name}** is {term} hoisted.")

    @role.command(name='rename', aliases=['name'])
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.has_guild_permissions(manage_roles=True)
    async def role_rename(self, ctx: MyContext, role: RoleConverter, *, name: str):
        """Rename a role's name."""

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to edit this role due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        oldname = role.name
        await role.edit(name=name)
        await ctx.send(f"Renammed from **{oldname}** to **{name}**.", embed=await self.show_roleinfo(role))

    @role.command(name='create')
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.has_guild_permissions(manage_roles=True)
    async def role_create(
        self, 
        ctx: MyContext, 
        color: Optional[discord.Color] = discord.Color.default(),
        hoist: Optional[bool] = False,
        *,
        name: str
    ):
        """Create a new role."""

        if len(ctx.guild.roles) >= 250:
            raise commands.BadArgument("This server has reached the maximum role limit: [250/250]")

        role = await ctx.guild.create_role(name=name, colour=color, hoist=hoist, reason=f'Role create command invoked by: {ctx.author} (ID: {ctx.author.id})')
        await ctx.send(f"**{role.name}** created.", embed=await self.show_roleinfo(role))

    @role.command(name='in')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_in(self, ctx: MyContext, base_role: RoleConverter, *, target_role: RoleConverter):
        """Add a role to members of another role."""

        if target_role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to add roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{target_role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{target_role.name}` position: {target_role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to add **{target_role.name}** to **{len(base_role.members)}** members.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to add **{target_role.name}** to **{len(base_role.members)}** members.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for human in base_role.members:
                if not can_execute_action(ctx, ctx.author, human):
                    failed += 1
                    continue

                if target_role in human.roles:
                    already_has += 1
                    continue

                try:
                    await human.add_roles(target_role, reason=f'Role-in invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully added **{target_role.name}** to {success}/{len(base_role.members)} members."
        if already_has:
            to_send += f"{already_has} members already had **{target_role.name}**"
        if failed:
            to_send += f"Failed to add **{target_role.name}** to {failed} members due to role hierarchy or permission errors."

        await ctx.send(to_send)


    @role.command(name='rin')
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.check(Cooldown(1, 120, 1, 90, commands.BucketType.guild))
    async def role_rin(self, ctx: MyContext, base_role: RoleConverter, *, target_role: RoleConverter):
        """Remove a role from members of another role."""

        if target_role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to remove roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{target_role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{target_role.name}` position: {target_role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        confirm = await ctx.confirm(f"Are you sure you want to remove **{target_role.name}** from **{len(base_role.members)}** members.")
        if confirm is False:
            raise commands.BadArgument("Canceled.")
        if confirm is None:
            raise commands.BadArgument("Timed out.")

        if ctx.guild.chunked is False:
            await ctx.guild.chunk()

        await ctx.send(f"Beginning to remove **{target_role.name}** from **{len(base_role.members)}** members.")
        
        success, failed, already_has = 0, 0, 0

        async with ctx.typing():
            for human in base_role.members:
                if not can_execute_action(ctx, ctx.author, human):
                    failed += 1
                    continue

                if not target_role in human.roles:
                    already_has += 1
                    continue

                try:
                    await human.remove_roles(target_role, reason=f'Role-rin invoked by: {ctx.author} (ID: {ctx.author.id})')
                    success += 1
                except discord.HTTPException:
                    failed += 1

        to_send = ""
        if success:
            to_send += f"Successfully removed **{target_role.name}** from {success}/{len(base_role.members)} members."
        if already_has:
            to_send += f"{already_has} members didn't even have **{target_role.name}**"
        if failed:
            to_send += f"Failed to remove **{target_role.name}** from {failed} members due to role hierarchy or permission errors."

        await ctx.send(to_send)

    @commands.Cog.listener()
    async def on_temprole_timer_complete(self, timer: Timer):
        guild_id, author_id, role_id, member_id = timer.args

        await self.bot.wait_until_ready()
        
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return # If we can't even find the guild we can't proceed

        role = guild.get_role(role_id)
        if role is None:
            return # there's nothing to add if the role is None

        member = await self.bot.get_or_fetch_member(guild, member_id)
        if member is None:
            return # member doesn't even exist

        moderator = await self.bot.get_or_fetch_member(guild, author_id)
        if moderator is None:
            try:
                moderator = await self.bot.fetch_user(author_id)
            except:
                # moderator request failed (somehow)
                moderator = f"Mod ID: {author_id}"
            else:
                moderator = f"{moderator} (ID: {author_id})"
        else:
            moderator = f'{moderator} (ID: {author_id})'

        try:
            await member.remove_roles(role, reason=f'Automatic temprole timer made on {timer.created_at} by {moderator}')
        except (discord.Forbidden, discord.HTTPException):
            pass # Either I don't have permissions at this time or removing the roles failed

    @commands.command(name='temprole', usage='<member> <duration> <role>')
    @commands.check(Cooldown(2, 10, 2, 8, commands.BucketType.member))
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def temprole(
        self, 
        ctx: MyContext, 
        member: discord.Member, 
        duration: FutureTime,
        *,
        role: RoleConverter
    ):
        """Adds a role to a member and removes it after the specified duration"""

        if role in member.roles:
            return await ctx.send("This member already has that role. \nIf you want to extend the temprole duration remove the role first.")

        if role.position > ctx.guild.me.top_role.position:
            to_send = ""
            to_send += (
                f"\🔴 I am unable to remove roles due to discord hierarchy rules."
                f"\nMy top role's position ({ctx.guild.me.top_role.mention}) is lower than `@{role.name}`"
                f"\n\nMy top role position: {ctx.guild.me.top_role.position} • `@{role.name}` position: {role.position}"
                f"\n\nPlease move my top role higher to make this command work!"
            )
            raise commands.BadArgument(to_send)

        if not can_execute_action(ctx, ctx.author, member):
            return await ctx.send('You are not high enough in role hierarchy to give roles to this member.')

        reminder_cog = ctx.bot.get_cog('utility')
        if reminder_cog is None:
            return await ctx.send('This function is not available at this time. Try again later.')

        try:
            timer = await reminder_cog.create_timer(
                duration.dt,
                "temprole",
                ctx.guild.id,
                ctx.author.id,
                role.id,
                member.id,
                connection=ctx.bot.db,
                created_at=ctx.message.created_at
            )
        except Exception as e:
            return await ctx.send(str(e))

        await member.add_roles(role, reason=f'Temprole command invoked by: {ctx.author} (ID: {ctx.author.id})')

        embed = Embed()
        embed.colour = discord.Colour.blue()
        embed.description = "__**Temporary role added**__"\
            f"\n{member.mention} was granted the {role.mention} role for {human_timedelta(duration.dt+datetime.timedelta(seconds=.4), accuracy=50)}"
        await ctx.send(embed=embed)

    @staticmethod
    def is_cancerous(text: str) -> bool:
        for segment in text.split():
            for char in segment:
                if not (char.isascii() and char.isalnum()):
                    return True
        return False

    @staticmethod
    def strip_accs(text):
        try:
            text = unicodedata.normalize("NFKC", text)
            text = unicodedata.normalize("NFD", text)
            text = unidecode.unidecode(text)
            text = text.encode("ascii", "ignore")
            text = text.decode("utf-8")
        except Exception as e:
            print(e)
        return str(text)

    async def nick_maker(self, old_shit_nick: str):
        old_shit_nick = self.strip_accs(old_shit_nick)
        new_cool_nick = re.sub("[^a-zA-Z0-9 \n.]", "", old_shit_nick)
        new_cool_nick = " ".join(new_cool_nick.split())
        new_cool_nick = stringcase.lowercase(new_cool_nick)
        new_cool_nick = stringcase.titlecase(new_cool_nick)
        if len(new_cool_nick.replace(" ", "")) <= 1 or len(new_cool_nick) > 32:
            new_cool_nick = "simp name"
        return new_cool_nick

    @commands.command(aliases=['dc'])
    @commands.has_guild_permissions(manage_nicknames=True)
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    async def decancer(self, ctx: MyContext, *, member: discord.Member):
        """Remove special/cancerous characters from a user's nickname."""

        old_nick = member.display_name
        if not self.is_cancerous(old_nick):
            embed = Embed(color=discord.Colour.red())
            embed.description = "**%s**'s nickname is already decancered." % member
            return await ctx.send(embed=embed)

        new_nick = await self.nick_maker(old_nick)
        if old_nick.lower() != new_nick.lower():
            try:
                await member.edit(nick=new_nick, reason=f'Decancer command invoked by: {ctx.author} (ID: {ctx.author.id})')
            except discord.Forbidden:
                raise commands.BotMissingPermissions(['manage_nicknames'])
            else:
                em = Embed(title='Decancer command', color=discord.Colour.green())
                em.set_author(name=member, icon_url=member.display_avatar.url)
                em.add_field(name='Old nick', value=old_nick, inline=False)
                em.add_field(name='New nick', value=new_nick, inline=False)
                return await ctx.send(embed=em)
        else:
            embed = Embed(color=discord.Colour.red())
            embed.description = "**%s**'s nickname is already decancered." % member
            return await ctx.send(embed=embed)

    @commands.command(aliases=['nick'])
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.has_guild_permissions(manage_nicknames=True)
    async def nickname(self, ctx: MyContext, member: Optional[discord.Member], *, nickname: Optional[str]):
        """Change a member's nickname. 
        
        Passing in no member will change my nickname.
        Passing in no nickname will remove a nickname if applicable.
        """
        member = member or ctx.guild.me
        await member.edit(nick=nickname, reason=f'Nickname command invoked by: {ctx.author} (ID: {ctx.author.id})')

        term = "my" if member == ctx.guild.me else f"{member.mention}'s"
        first_term = "Changed" if nickname else "Reset"
        new_nick = "." if nickname is None else " to **%s**." % nickname 

        em = Embed()
        em.set_author(name=member, icon_url=member.display_avatar.url)
        em.description = f"{first_term} {term} nickname{new_nick}"
        return await ctx.send(embed=em)

    @commands.command(name='nuke-channel', aliases=['nuke'])
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_channels=True)
    async def nuke_channel(self, ctx: MyContext, *, channel: Optional[discord.TextChannel]):
        """Nuke a text channel.
        
        This deletes the channel and creates the same channel again.
        """
        channel = channel or ctx.channel

        confirm = await ctx.confirm(f'Are you sure you want to nuke {channel.mention}', timeout=30.0)
        if confirm is False:
            return await ctx.send("Canceled.")
        if confirm is None:
            return await ctx.send("Timed out.")

        new_channel = await channel.clone(name=channel.name)
        await ctx.ghost_ping(ctx.author, channel=new_channel)

        try:
            await channel.delete(reason=f'Nuke command invoked by: {ctx.author} (ID: {ctx.author.id})')
        except (discord.HTTPException, discord.Forbidden) as e:
            return await ctx.send(f"Had an issue with deleting this channel. {e}")

        await new_channel.send(f"Nuke-command ran by: {ctx.author}")

    @commands.group(case_insensitive=True, invoke_without_command=True)
    @commands.has_guild_permissions(manage_messages=True)
    async def note(self, ctx: MyContext):
        """Base command for managing notes.
        
        Moderators/admins can add notes to members.
        For more personal notes please use `reminder` or `todo`.

        Normal members can view their notes with `notes`
        """
        await ctx.help()

    @note.command(name='add', aliases=['+'])
    @commands.has_guild_permissions(manage_messages=True)
    async def note_add(self, ctx: MyContext, member: discord.Member, *, note: commands.clean_content):
        """Add a note to a member's notes."""

        async with ctx.typing():
            id = await self.bot.db.fetch("SELECT MAX(id) FROM notes")
            if id[0].get('max') is None:
                id = 1
            else:
                id = int(id[0].get('max')) + 1
            await self.bot.db.execute(
                "INSERT INTO notes (id, user_id, text, added_time, author_id) VALUES ($1, $2, $3, $4, $5)", 
                id, member.id, note, (discord.utils.utcnow().replace(tzinfo=None)), ctx.author.id
            )      
            embed = Embed(color=discord.Color.green())
            embed.description = f"{self.bot.check} __**Note taken.**__ \n> {note}"
            embed.set_footer(text='Note ID: %s' % id)
            return await ctx.send(embed=embed)
        
    @note.command(name='remove', aliases=['-'])
    @commands.has_guild_permissions(manage_messages=True)
    async def note_remove(self, ctx: MyContext, *, id: int):
        """Remove a note by it's id.
        
        Use `note list` to show a member's notes."""

        async with ctx.typing():
            note = await self.bot.db.fetchval("SELECT text FROM notes WHERE id=$1", id)
            if not note:
                raise commands.BadArgument("A note with that ID was not found. Use `%snote list [member]` to show a member's notes." % ctx.clean_prefix)

            await self.bot.db.execute("DELETE FROM notes WHERE id = $1", id)

            embed = Embed(color=discord.Colour.red())
            embed.description = f"{self.bot.cross} __**Deleted note {id}.**__\n> {note}"
            return await ctx.send(embed=embed)

    @note.command(name='list', aliases=['show'])
    @commands.has_guild_permissions(manage_messages=True)
    async def note_list(self, ctx: MyContext, *, member: Optional[discord.Member]):
        """
        Show a member's notes.
        
        Don't pass in a member to show your own notes.
        """
        member = member or ctx.author
        
        async with ctx.typing():
            notes = await self.bot.db.fetch("SELECT (id, text, added_time, author_id) FROM notes WHERE user_id = $1", member.id)
            if not notes:
                raise commands.BadArgument("No notes were found for this member. Use `%snote add <member> <note>` to add a note." % ctx.clean_prefix)
            
            embed = Embed()
            embed.set_author(name="%s's notes" % member, icon_url=member.display_avatar.url)
            embed.set_footer(text=f"{len(notes)} note{'s.' if len(notes) > 1 else '.'}")

            for note in notes:
                note_id : int = note['row'][0]
                note_text : str = note['row'][1]
                note_added_time : datetime.datetime = pytz.utc.localize(note['row'][2])
                author_id : int = note['row'][3]

                embed.add_field(name='Note #%s' % note_id, value=f'From <@{author_id}> {discord.utils.format_dt(note_added_time, "R")} \n> {note_text}')

            return await ctx.send(embed=embed)

    @note.command(name='clear', aliases=['wipe'])
    @commands.has_guild_permissions(manage_messages=True)
    async def note_clear(self, ctx: MyContext, *, member: discord.Member):
        """Clear a member's note."""

        async with ctx.typing():
            data = await self.bot.db.fetch("SELECT * FROM notes WHERE user_id = $1", member.id)
            if not data:
                raise commands.BadArgument("No notes were found for this member. Use `%snote add <member> <note>` to add a note." % ctx.clean_prefix)
            
        confirm = await ctx.confirm(f"This will clear **{len(data)}** from {member}'s notes, are you sure?", timeout=30)
        if confirm is None:
            return await ctx.send("Timed out.")
        if confirm is False:
            return await ctx.send("Canceled.")

        async with ctx.typing():
            await self.bot.db.execute("DELETE FROM notes WHERE user_id = $1", member.id)

            return await ctx.send(f"Successfully cleared **{len(data)}** notes from {member}")

    @note.command(name='redo', aliases=['re'])
    @commands.has_guild_permissions(manage_messages=True)
    async def note_redo(self, ctx: MyContext, member: discord.Member, *, note: str):
        """Clear a member's notes and replace with a single note."""

        await ctx.invoke(self.note_clear, member=member)
        await ctx.invoke(self.note_add, member=member, note=note)
    
    @commands.command(aliases=['mynotes'])
    async def notes(self, ctx: MyContext):
        """View your own notes."""
        await ctx.invoke(self.note_list, member=ctx.author)

    @commands.command(name='grant', aliases=['grant-permissions'])
    @commands.has_guild_permissions(administrator=True)
    @commands.bot_has_guild_permissions(manage_roles=True, manage_channels=True)
    async def grant_permissions(self, ctx: MyContext, entity: Union[discord.Member, discord.Role], *perms: str):
        """
        Grant an entity certain permissions.
        
        Entity may be a member or a role.
        Make sure my top role is above that target role if entity is a role.

        If an entity is a role it edits the permissions on that role.
        If an entity is a member it edits the current channel's permissions.
        """
        
        if isinstance(entity, discord.Member):
            if not can_execute_action(ctx, ctx.author, entity):
                raise commands.BadArgument("You are not high enough in role hierarchy to grant permissions to this member.")

            overwrites = discord.PermissionOverwrite()
            perms_cleaned = []
            for perm in perms:
                if perm.lower().replace("server", "guild").replace(" ", "_") not in dict(discord.Permissions()):
                    raise commands.BadArgument(f"Invaild permission: {perm}")
                overwrites.update(**(dict(perm=True)))
                perms_cleaned.append(perm.title())
                
            overwrites = {entity: overwrites}
            
            to_send = ", ".join(["`%s`" % perm for perm in perms_cleaned])

            await ctx.channel.edit(overwrites=overwrites)
            return await ctx.send(f"Granted {to_send} to {entity}")

        elif isinstance(entity, discord.Role):
            permissions = discord.Permissions()
            if entity.position >= ctx.author.top_role.position:
                if ctx.author == ctx.guild.owner:
                    pass
                else:
                    raise commands.BadArgument("You are not high enough in role hierarchy to grant permissions to this role.")
            
            to_append = []

            for perm in perms:
                if perm not in dict(discord.Permissions()):
                    raise commands.BadArgument("Invaild permission: %s" % perm)

                setattr(permissions, perm, True)
                to_append.append(perm.title().replace("_", " "))

            to_send = ", ".join(["`%s`" % x for x in to_append])
            
            await entity.edit(permissions=permissions)
            return await ctx.send(f"Granted {to_send} to {entity}")

                