import os
import errno
import time
import numpy
import pandas
import json
from twitchio.ext import commands
from twitchio.dataclasses import User

import read

with open("config.json") as fin:
    opts = json.load(fin)

bot = commands.Bot(**opts)

_ROOT = {"darkslash88"}
# add additional admin names here
_AUTHORIZED = _ROOT | {"fusoyeahhh", "crackboombot"}

def _write(ctx, strn, prefix="BCFBot>"):
    pass

def _authenticate(ctx):
    print(ctx.author.name, _AUTHORIZED)
    print(ctx.author.name in _AUTHORIZED)
    return ctx.author.name in _AUTHORIZED

_AREA_INFO = pandas.read_csv("data/bc_fantasy_data_areas.csv")
_BOSS_INFO = pandas.read_csv("data/bc_fantasy_data_bosses.csv")
_CHAR_INFO = pandas.read_csv("data/bc_fantasy_data_chars.csv")
_MAP_INFO = pandas.read_csv("data/map_ids.csv")
_MAP_INFO["id"] = [int(n, 16) for n in _MAP_INFO["id"]]
_MAP_INFO = _MAP_INFO.set_index("id")

COMMANDS = {}

HISTORY = {}

LOOKUPS = {
    "area": ("Area", _AREA_INFO),
    "char": ("Character", _CHAR_INFO),
    "boss": ("Boss", _BOSS_INFO),
}

_USERS = {}

_CONTEXT = {
    "area": None,
    "boss": None,
    #"skill": None,
    #"character": None
}

#
# Parsing
#
def convert_buffer_to_commands(logf, **kwargs):
    cmds = []
    last_status = kwargs.get("last_status", {})
    for status in sorted(logf, key=lambda l: l["frame"]):
        # check for map change
        if status["map_id"] != last_status.get("map_id", None):
            cmds.append(f"!set area={status['map_id']}")
            print("emu>", cmds[-1])

        # check for boss encounter
        if status["in_battle"] and status["eform_id"] != last_status.get("eform_id", None) \
            and int(status["eform_id"]) in _BOSS_INFO["Id"].values:
            cmds.append(f"!set boss={status['eform_id']}")
            print("emu>", cmds[-1])

        # check for miab
        if status["in_battle"] and status["eform_id"] != last_status.get("eform_id", None) \
            and int(status["eform_id"]) == int(last_status.get("miab_id", -1)):
            cmds.append(f"!event miab")
            print("emu>", cmds[-1])

        # check for kills
        lkills = last_status.get("kills", {})
        for char, k in status.get("kills", {}).items():
            diff = k - lkills.get(char, 0)
            if diff > 0:
                # FIXME: should probably in_check battle status
                etype = "boss" if int(status["eform_id"]) in _BOSS_INFO["Id"].values else "enemy"
                cmds.append(f"!event {etype}kill {char} {diff}")
                print("emu>", cmds[-1])

        # check for deaths
        ldeaths = last_status.get("deaths", {})
        for char, k in status.get("deaths", {}).items():
            diff = k - ldeaths.get(char, 0)
            if diff > 0:
                cmds.append(f"!event chardeath {char} {diff}")
                print("emu>", cmds[-1])

        last_status = status

    print("Last status:", last_status)

    return cmds, last_status

#
# Utils
#

def _set_context(content):
    try:
        selection = " ".join(content.split(" ")[1:])
        cat, item = selection.split("=")
        print(cat, item)

        # Need a preliminary mapid to area setting
        if cat == "area" and item.isdigit():
            item = int(item)
            if item in _MAP_INFO.index:
                item = _MAP_INFO.loc[item]["scoring_area"]
            else:
                raise ValueError(f"No valid area mapping for id {item}")

        if cat == "boss" and item.isdigit():
            item = int(item)
            if item in _BOSS_INFO["Id"]:
                item = _BOSS_INFO.set_index("Id").loc[item]["Boss"]
            else:
                raise ValueError(f"No valid boss mapping for id {item} (this may be intended)")

        lookup, info = LOOKUPS[cat]
        # FIXME: zozo vs. mt. zozo
        item = _check_term(item, lookup, info)

        print(cat, item, _CONTEXT)
        if cat in _CONTEXT:
            _CONTEXT[cat] = item

    except Exception as e:
        print(e)
        return False

    return True

def _chunk_string(inlist, joiner=", "):
    if len(inlist) == 0:
        return
    assert max([*map(len, inlist)]) < 500, \
                                "Can't fit all messages to buffer length"

    outstr = str(inlist.pop(0))
    while len(inlist) >= 0:
        if len(inlist) == 0:
            yield outstr
            return
        elif len(outstr) + len(joiner) + len(inlist[0]) >= 500:
            yield outstr
            outstr = inlist.pop(0)
            continue

        outstr += joiner + str(inlist.pop(0))

def _check_term(term, lookup, info, full=False):
    _term = term.replace("(", r"\(").replace(")", r"\)")
    found = info[lookup].str.lower().str.contains(_term.lower())
    found = info.loc[found]

    if len(found) > 1:
        found = info[lookup].str.lower() == _term.lower()
        found = info.loc[found]

    if len(found) != 1:
        raise KeyError()
    if full:
        return found
    return str(found[lookup].iloc[0])

def _check_user(user):
    return user in _USERS

def search(term, lookup, info):
    _term = term.replace("(", r"\(").replace(")", r"\)")
    found = info[lookup].str.lower().str.contains(_term.lower())
    found = info.loc[found]
    print(found)
    if len(found) > 1:
        found = info[lookup].str.lower() == _term.lower()
        found = info.loc[found]

    if len(found) > 1:
        found = ", ".join(found[lookup])
        return f"Found more than one entry ({found}) for {term}"
    elif len(found) == 0:
        return f"Found nothing matching {term}"
    else:
        return str(found.to_dict(orient='records')[0])[1:-1]

#
# Bot commands
#

@bot.event
async def event_ready():
    print("HELLO HUMAN, I AM BCFANTASYBOT. FEAR AND LOVE ME.")
    bot._skip_auth = False
    bot._last_status = {}
    ws = bot._ws

@bot.command(name='doarena')
async def _arena(ctx):
    await ctx.send('!arena')

@bot.event
async def event_message(ctx):
    #if (ctx.author.name.lower() == "crackboombot" and
        #"Type !arena to start" in ctx.content):
        #ctx.content = '!doarena' + " " + ctx.content

    print(ctx.content)

    if ctx.content.startswith("!"):
        command = ctx.content.split(" ")[0][1:]
        if command in bot.commands:
            current_time = int(time.time() * 1e3)
            HISTORY[current_time] = ctx.content

            await bot.handle_commands(ctx)

    # Trigger a check of the local buffer
    buff = []
    try:
        buff = read.read_local_queue()
    except AttributeError:
        pass

    # Read in emulator log
    try:
        cmds = read.parse_log_file(last_frame=bot._last_status.get("frame", -1))
        cmds, last = convert_buffer_to_commands(cmds, last_status=bot._last_status)
        bot._last_status = last
        buff += cmds
    except Exception as e:
        print(e)
        print("Couldn't read logfile")

    for line in filter(lambda l: l, buff):
        bot._skip_auth = True
        # Co-op ctx
        ctx.content = line
        # HACKZORS
        ctx.author._name = "crackboombot"
        #ctx.author = User(bot._ws, name="crackboombot")

        command = ctx.content.split(" ")[0][1:]
        if command in bot.commands:
            current_time = int(time.time() * 1e3)
            HISTORY[current_time] = ctx.content
            print(f"Internally sending command as {ctx.author.name}: '{ctx.content}'")
            await bot.handle_commands(ctx)
    bot._skip_auth = False

@bot.command(name='hi')
async def hi(ctx):
    await ctx.send('/me HELLO HUMAN, I AM BCFANTASYBOT. FEAR --- EXCEPT NEBEL AND CJ, WHO ARE PRETTY COOL PEOPLE --- AND LOVE ME.')

@bot.command(name='blame')
async def blame(ctx):
    blame = ctx.content
    name = blame.split(" ")[-1].lower()
    await ctx.send(f'/me #blame{name}')

#
# User-based commands
#

@bot.command(name='register')
async def register(ctx):
    """
    !register -> no arguments, adds user to database
    """
    user = ctx.author.name
    if _check_user(user):
        await ctx.send(f"@{user}, you are already registered.")
        return

    # Init user
    _USERS[user] = {"score": 1000}
    await ctx.send(f"@{user}, you are now registered, and have "
                   f"{_USERS[user]['score']} points to use. "
                    "Choose a character (char), area, and boss with "
                    "!select [category]=[item]")
COMMANDS["register"] = register

@bot.command(name='userinfo')
async def userinfo(ctx):
    """
    !userinfo --> no arguments, returns user selections
    """
    user = ctx.author.name
    if not _check_user(user):
        await ctx.send(f"@{user}, you are not registered, use !register first.")
        return

    # Return user selections
    info = " ".join([f"({k} | {v})" for k, v in _USERS[user].items()])
    await ctx.send(f"@{user}: {info}")
COMMANDS["userinfo"] = userinfo

@bot.command(name='userscore')
async def userscore(ctx):
    """
    !userscore --> no arguments, returns user score
    """
    user = ctx.author.name
    if not _check_user(user):
        await ctx.send(f"@{user}, you are not registered, use !register first.")
        return

    await ctx.send(f"@{user}, score: {_USERS[user]['score']}")
COMMANDS["userscore"] = userscore

@bot.command(name='select')
async def select(ctx):
    """
    !select [area|boss|char]=[selection] set the selection for a given category. Must have enough points to pay the cost.
    """
    user = ctx.author.name
    if user not in _USERS:
        await ctx.send(f"@{user}, you are not registered, use !register first.")
        return

    try:
        selection = " ".join(ctx.content.lower().split(" ")[1:])
        cat, item = selection.split("=")
        cat = cat.lower()

        if cat in LOOKUPS:
            lookup, info = LOOKUPS[cat]
            try:
                item = _check_term(item, lookup, info)
            except KeyError:
                await ctx.send(f"@{user}: that {cat} selection is invalid.")
                return
            cost = info.set_index(lookup).loc[item]["Cost"]

            _user = _USERS[user]
            if cost <= _user["score"]:
                _user["score"] -= int(cost)
            else:
                await ctx.send(f"@{user}: insufficient funds.")
                return

        elif _authenticate(ctx) and cat == "score":
            item = int(item)
        else:
            await ctx.send(f"@{user}: {cat} is an invalid category")
            return

        _USERS[user][cat] = item
        await ctx.send(f"@{user}: got it. Your selection for {cat} is {item}")
        return

    except Exception as e:
        print("Badness: " + str(e))

    await ctx.send(f"Sorry @{user}, that didn't work.")
COMMANDS["select"] = select

#
# Context commands
#

# Areas
@bot.command(name='listareas')
async def listareas(ctx):
    """
    !listareas --> no arguments, list all available areas
    """
    info = [f"{i[0]} ({i[1]})"
                for _, i in _AREA_INFO[["Area", "Cost"]].iterrows()]
    for outstr in _chunk_string(info):
        await ctx.send(outstr)
COMMANDS["listareas"] = listareas

@bot.command(name='areainfo')
async def areainfo(ctx):
    """
    !areainfo [area] list information about given area
    """
    area = " ".join(ctx.content.split(" ")[1:]).lower()
    print(area)
    await ctx.send(search(area, "Area", _AREA_INFO))
COMMANDS["areainfo"] = areainfo

# Bosses
@bot.command(name='listbosses')
async def listbosses(ctx):
    """
    !listbosses --> no arguments, list all available bosses
    """
    info = [f"{i[0]} ({i[1]})"
                for _, i in _BOSS_INFO[["Boss", "Cost"]].iterrows()]
    for outstr in _chunk_string(info):
        await ctx.send(outstr)
COMMANDS["listbosses"] = listbosses

@bot.command(name='bossinfo')
async def bossinfo(ctx):
    """
    !bossinfo [boss] list information about given boss
    """
    boss = " ".join(ctx.content.split(" ")[1:]).lower()
    print(boss)
    await ctx.send(search(boss, "Boss", _BOSS_INFO))
COMMANDS["bossinfo"] = bossinfo

# Characters
@bot.command(name='listchars')
async def listchars(ctx):
    """
    !listchars --> no arguments, list all available characters
    """
    info = [f"{i[0]} ({i[1]})"
                for _, i in _CHAR_INFO[["Character", "Cost"]].iterrows()]
    for outstr in _chunk_string(info):
        await ctx.send(outstr)
COMMANDS["listchars"] = listchars

@bot.command(name='charinfo')
async def charinfo(ctx):
    """
    !charinfo [char] list information about given char
    """
    char = " ".join(ctx.content.split(" ")[1:]).lower()
    print(char)
    await ctx.send(search(char, "Character", _CHAR_INFO))
COMMANDS["charinfo"] = charinfo

# General
@bot.command(name='context')
async def context(ctx):
    """
    !context --> no arguments, list the currently active area and boss
    """
    await ctx.send(str(_CONTEXT).replace("'", "").replace("{", "").replace("}", ""))
COMMANDS["context"] = context

@bot.command(name='leaderboard')
async def leaderboard(ctx):
    """
    !context --> no arguments, list the current players and their scores.
    """
    s = [f"@{user}: {attr['score']}" for user, attr in
                    reversed(sorted(_USERS.items(),
                                    key=lambda kv: kv[1]['score']))]
    for os in _chunk_string(s, joiner=" | "):
        await ctx.send(os)
COMMANDS["context"] = context

@bot.command(name='nextarea')
async def nextarea(ctx):
    user = ctx.author.name
    if not (bot._skip_auth or _authenticate(ctx)):
        await ctx.send(f"I'm sorry, @{user}, I can't do that...")
        return

    area = _CONTEXT["area"] or "Narshe (WoB)"
    # FIXME: catch OOB
    idx = numpy.roll(_AREA_INFO["Area"] == area, 1)
    new_area = str(_AREA_INFO["Area"][idx].iloc[0])
    if _set_context(f"!set area={new_area}"):
        return

    if not bot._skip_auth:
        await ctx.send(f"Sorry @{user}, that didn't work.")

@bot.command(name='nextboss')
async def nextboss(ctx):
    user = ctx.author.name
    if not (bot._skip_auth or _authenticate(ctx)):
        await ctx.send(f"I'm sorry, @{user}, I can't do that...")
        return

    boss = _CONTEXT["boss"] or "Whelk"
    # FIXME: catch OOB
    idx = numpy.roll(_BOSS_INFO["Boss"] == boss, 1)
    new_area = str(_BOSS_INFO["Boss"][idx].iloc[0])
    if _set_context(f"!set boss={new_area}"):
        return

    if not bot._skip_auth:
        await ctx.send(f"Sorry @{user}, that didn't work.")

@bot.command(name='set')
async def _set(ctx):
    user = ctx.author.name
    if not (bot._skip_auth or _authenticate(ctx)):
        await ctx.send(f"I'm sorry, @{user}, I can't do that...")
        return

    if _set_context(ctx.content):
        return
    if not bot._skip_auth:
        await ctx.send(f"Sorry @{user}, that didn't work.")

# FIXME: these are the columns of the individual files
_EVENTS = {
    frozenset({"gameover", "chardeath", "miab", "backattack", "cantrun"}): "area",
    frozenset({"gameover", "bchardeath"}): "boss",
    frozenset({"enemykill", "bosskill", "buff", "debuff"}): "char"
}

@bot.command(name='give')
async def give(ctx):
    """
    !give --> [list of people to give to] [amt]
    """
    user = ctx.author.name
    if not (bot._skip_auth or _authenticate(ctx)):
        await ctx.send(f"I'm sorry, @{user}, I can't do that...")
        return

    cmd = ctx.content.split(" ")[2:]
    if len(cmd) == 1:
        # Give everyone points
        for user in _USERS:
            user["score"] += int(cmd[0])
    elif len(cmd) > 1:
        # Give specified chatters points
        pts = int(cmd[-1])
        for user in cmd[:-1]:
            if user in _USERS:
                _USERS[user]["score"] += int(cmd[0])
COMMANDS["give"] = give

@bot.command(name='event')
async def event(ctx):
    user = ctx.author.name
    if not (bot._skip_auth or _authenticate(ctx)):
        await ctx.send(f"I'm sorry, @{user}, I can't do that...")
        return

    """
    print(">>>", _CONTEXT["area"])
    print(">>>", set(_AREA_INFO["Area"]))
    if _CONTEXT["area"] is None or
       _CONTEXT["area"] not in set(_AREA_INFO["Area"]):
        await ctx.send("Invalid area in context. Please reset.")
    """

    try:
        event = ctx.content.lower().split(" ")[1:]
        event, args = event[0], event[1:]
        cats = {v for k, v in _EVENTS.items() if event in k}
        if len(cats) == 0:
            raise IndexError()
    except IndexError:
        await ctx.send(f"Invalid event command: {event}, {'.'.join(args)}")
        return

    print(event, args, cats)
    for cat in cats:
        for user, sel in _USERS.items():
            #print(user, sel.get("area", "").lower(), _CONTEXT["area"].lower())

            lookup, info = LOOKUPS[cat]
            multi = 1
            if cat in {"boss", "area"}:
                has_item = sel.get(cat, "").lower() == _CONTEXT[cat].lower()
                item = _check_term(_CONTEXT[cat], lookup, info, full=True)
            elif cat == "char":
                has_item = sel.get(cat, "").lower() == args[0].lower()
                item = args[0]
                if len(args) > 1:
                    multi = int(args[1])
                item = _check_term(item, lookup, info, full=True)
            #print(item, user)

            _score = sel["score"]
            # FIXME, just map to appropriate column in row
            if event == "gameover" and has_item:
                sel["score"] += int(item["Gameover"])
            elif event == "miab" and has_item:
                sel["score"] += int(item["MIAB"])
            elif event == "chardeath" and has_item:
                sel["score"] += int(item["Kills Character"])
            elif event == "bchardeath" and has_item:
                sel["score"] += int(item["Kills Character"])
            elif event == "enemykill" and has_item:
                sel["score"] += int(item["Kills Enemy"]) * multi
            elif event == "bosskill" and has_item:
                sel["score"] += int(item["Kills Boss"])
            elif event == "buff" and has_item:
                sel["score"] += int(item["Buff"])
            elif event == "debuff" and has_item:
                sel["score"] += int(item["Debuff"])
            #elif event == "backattack" and has_item:
                #sel["score"] += 1
            #elif event == "cantrun" and has_item:
                #sel["score"] += 2
            print(f"\t{event}, {user} {sel['score'] - _score}")

#
# Help commands
#
@bot.command(name='help')
async def _help(ctx):
    """
    This command.
    """
    user = ctx.author.name
    cnt = ctx.content.lower().split(" ")
    cnt.pop(0)
    if not cnt:
        await ctx.send(f"Available commands: {' '.join(COMMANDS.keys())}. Use '!help cmd' (no excl. point on 'cmd) to get more help.")
    arg = cnt.pop(0)
    if arg not in COMMANDS:
        await ctx.send(f"@{user}, that's not a command I have help for. Available commands: {' '.join(COMMANDS.keys())}.")
        return
    doc = COMMANDS[arg]._callback.__doc__
    print(COMMANDS[arg])
    await ctx.send(f"help | {arg}: {doc}")
COMMANDS["help"] = _help

@bot.command(name='bcf')
async def explain(ctx):
    """
    Explain what do.
    """
    user = ctx.author.name
    for outstr in _chunk_string([f"@{user}: Use '!register' to get started.",
                     "You'll start with 1000 points to spend.",
                     "You will !select a character (!listchars), boss (!listbosses), and area (!listareas).",
                     "The chosen character will accrue points for killing enemies and bosses.",
                     "Bosses get points for kills and gameovers.",
                     "Areas get points for MIAB, character kills, and gameovers."],
                     joiner=' '):
        await ctx.send(outstr)
COMMANDS["bcf"] = explain

if __name__ == "__main__":
    import time
    import glob
    import json

    # find latest
    try:
        latest = sorted(glob.glob("user_data*.json"),
                        key=lambda f: os.path.getmtime(f))[-1]
        with open(latest, "r") as fin:
            _USERS = json.load(fin)
        print(_USERS)
    except IndexError:
        pass

    if os.path.exists("context.json"):
        with open("context.json", "r") as fin:
            _CONTEXT = json.load(fin)
        print(_CONTEXT)

    # for local stuff
    try:
        os.mkfifo("local")
    except OSError as oe:
        if oe.errno != errno.EEXIST:
            raise
    except AttributeError:
        pass

    bot.run()

    os.remove("local")

    with open("context.json", "w") as fout:
        json.dump(_CONTEXT, fout, indent=2)

    with open("history.json", "w") as fout:
        json.dump(HISTORY, fout, indent=2)

    time = int(time.time())
    with open(f"user_data_{time}.json", "w") as fout:
        json.dump(_USERS, fout, indent=2)
