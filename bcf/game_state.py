import os
import shutil
import glob
import datetime
import json
import logging

import pandas

from . import convert_buffer_to_commands, _check_term
from . import read
from .utils import export_to_gsheet


class GameState(object):

    # Context template
    _CONTEXT = {
        "area": None,
        "boss": None,
        "music": None
    }

    # FIXME: these are the columns of the individual files
    _EVENTS = {
        frozenset({"gameover", "chardeath", "miab", "backattack", "cantrun"}): "area",
        frozenset({"bgameover", "bchardeath"}): "boss",
        frozenset({"enemykill", "bosskill", "buff", "debuff"}): "char"
    }

    def __init__(self, bot, chkpt_dir="./checkpoint/", **kwargs):
        self._stream_status = kwargs.pop("stream_status", "./stream_status.txt")
        super().__init__()

        # FIXME: eventually we'll just *be* the bot. Just you wait...
        # opts = process_opts(config_file)
        #super().__init__(**opts)
        self._bot = bot

        # Where we keep our checkpointed user and game data
        #_CHKPT_DIR = opts.pop("checkpoint_directory", "./checkpoint/")
        self.chkpt_dir = chkpt_dir
        self.reset()

        # find latest
        udata_file = os.path.join(self.chkpt_dir, "user_data*.json")
        self._user_data = self.find_latest_user_data(udata_file)

        status_file = os.path.join(self.chkpt_dir, "_last_status.json")
        self._last_status = self.read_last_status(status_file)

        ctx_file = os.path.join(chkpt_dir, "../context.json")
        self._context = self.read_context(ctx_file)
        self._history = {}

        # Initialize all the game mechanics / info
        self.load_game_data()

        self.music_info, self.char_info = {}, {}
        self._flags, self._seed = None, None
        # _SPOILER_LOG = opts.pop("spoiler", None)
        #self.from_spoiler(spoiler_log)

        # If the flags are listed in the configuration file, they override all else
        #_FLAGS = opts.pop("flags", _FLAGS)
        # Same for seed
        #_SEED = opts.pop("seed", _SEED)
        # Season label is used for archival and tracking purposes
        #_SEASON_LABEL = opts.pop("season", None)

    def check_buffer(self, logfile="logfile.txt"):
        # Trigger a check of the local buffer
        buff = []

        if self._bot._status == "paused":
            logging.warning("check_buffer | State is paused; ignoring log.")
        else:
            try:
                # Read in emulator log
                cmds = read.parse_log_file(last_frame=self._last_status.get("frame", -1))
                logging.debug(f"Logfile read with {len(cmds)} commands.")
                # FIXME: Need to move convert into this module
                cmds, self._last_status = convert_buffer_to_commands(cmds, self, last_status=self._last_status)
                buff += cmds
                logging.debug(f"emu buffer length: {len(cmds)}")
            except Exception as e:
                logging.error(e)
                logging.error("check_buffer | Couldn't read logfile")

        logging.debug(f"Processing command buffer... status: {self._bot._status}")
        for line in filter(lambda l: l, buff):
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            self._history[current_time] = line

            command = line.split(" ")[0][1:]

            if command == "set":
                self._set_context(line)
            elif command == "event":
                event, args = self._validate_event(line)
                self.handle_event(event, *args)
                pass
            elif command in self._bot.commands:
                # FIXME: This is more a debug to see if it happens, remove when confident

                #await self._bot.handle_commands(ctx)
                logging.error(f"check_buffer | got command {command} from emu, but cannot process without twitch message")
            else:
                logging.error(f"check_buffer | got unknown command from emu buffer: {command}")

    def _set_context(self, content):
        """
        Set a value in the current game context.

        :param content: (string) twitch-style command, likely from the 'set' command.
        :return: (bool) whether or not the attempted context set was completed.
        """

        try:
            selection = " ".join(content.split(" ")[1:])
            cat, item = selection.split("=")
            logging.debug(f"Attempting to set {cat} to {item}.")

            # Preliminary mapid to area setting
            # These almost always come from the emulator indicating a map change
            if cat == "area" and item.isdigit():
                _item = int(item)
                if _item in self.map_info.index:
                    # FIXME: need to move this to a special handler function
                    # We don't change the context if on this map, since it can indicate a gameover
                    if _item == 5:
                        logging.info("Map id 5 detected, not changing area.")
                        return True

                    # South Figaro basement split map
                    # FIXME: There is assuredly more of these, so they should be captured in a function
                    elif _item == 89:
                        logging.info("Map id 89 (SF basement) detected, not changing area.")
                        return True

                    # Translate integer map id to the area to set in the context
                    item = self.map_info.loc[_item]["scoring_area"]

                    # This map id exists, but is not mapped to an area
                    # FIXME: This shouldn't be needed once we're set on the area mappings
                    if pandas.isna(item):
                        return True

                    logging.info(f"Area: {_item} => {item}")
                else:
                    # Log that the map id didn't have an entry in the lookup tables
                    # FIXME: raise an exception when we're more confident about the map => area lookup
                    logging.error(f"No valid area mapping for id {item}")
                    return True

            if cat == "boss" and item.isdigit():
                _item = int(item)
                if _item in set(self.boss_info["Id"]):
                    # Look up numeric id and get canonical boss name
                    item = self.boss_info.set_index("Id").loc[_item]["Boss"]
                    logging.info(f"Boss: {_item} => {item}")
                else:
                    # We raise this, but it's possible it's intended, so the caller will just get False instead
                    raise ValueError(f"No valid boss mapping for id {_item} (this may be intended)")

            lookup, info = self._lookups[cat]
            item = _check_term(item, lookup, info)

            # Actually set the item in the context
            # FIXME: do this through _set_context
            logging.debug((cat, item, self._context))
            if cat in self._context:
                self._context[cat] = item

            # Serialize the change, note that this doesn't seem to get picked up in restarts
            # FIXME: to method
            with open("../context.json", "w") as fout:
                json.dump(self._context, fout, indent=2)

        except Exception as e:
            # There's lots of reasons why this may not work, and it's not necessarily fatal, so we just log it and
            # let the caller know
            logging.error(e)
            return False

        # Indicate success
        return True

    def handle_event(self, event, *args):

        status_string = ""
        if self._stream_status:
            logging.debug("Attempting to write specifics to stream status.")
            status_string += f"{event}: " + " ".join(args) + " "

        cats = {v for k, v in self._EVENTS.items() if event in k}
        did_error = False
        logging.debug((event, args, cats))
        for cat in cats:
            for user, sel in self._user_data.items():
                # logging.info(user, sel.get("area", "").lower(), _CONTEXT["area"].lower())

                lookup, info = self._lookups[cat]
                multi = 1
                try:
                    if cat in {"boss", "area"}:
                        has_item = sel.get(cat, "").lower() == (self._context[cat] or "").lower()
                        item = _check_term(self._context[cat], lookup, info, full=True)
                    elif cat == "char":
                        has_item = sel.get(cat, "").lower() == args[0].lower()
                        item = _check_term(args[0], lookup, info, full=True)
                    if len(args) > 1:
                        multi = int(args[1])
                except Exception as e:
                    if not did_error:
                        did_error = True
                        logging.error(f"Failed lookup for {cat}: " + str(e))
                    continue
                # print(item, user)

                _score = sel["score"]
                # FIXME, just map to appropriate column in row
                if event in {"gameover", "bgameover"} and has_item:
                    sel["score"] += int(item["Gameover"])
                elif event == "miab" and has_item:
                    sel["score"] += int(item["MIAB"])
                elif event == "chardeath" and has_item:
                    sel["score"] += int(item["Kills Character"]) * multi
                elif event == "bchardeath" and has_item:
                    sel["score"] += int(item["Kills Character"]) * multi
                elif event == "enemykill" and has_item:
                    sel["score"] += int(item["Kills Enemy"]) * multi
                elif event == "bosskill" and has_item:
                    sel["score"] += int(item["Kills Boss"]) * multi
                elif event == "buff" and has_item:
                    sel["score"] += int(item["Buff"])
                elif event == "debuff" and has_item:
                    sel["score"] += int(item["Debuff"])
                # elif event == "backattack" and has_item:
                # sel["score"] += 1
                # elif event == "cantrun" and has_item:
                # sel["score"] += 2
                if self._stream_status:
                    score_diff = sel['score'] - _score
                    did_score = score_diff > 0
                    if did_score:
                        status_string += f"{user} +{score_diff} "
                        logging.debug("Wrote an item to stream status.")
                else:
                    logging.info(f"handle_event | \t{event}, {user} {sel['score'] - _score}")

    def write_status(self, fname):
        status = " | ".join([f"{cat.capitalize()}: {val}" for cat, val in self._context.items()])
        status = status.replace("Boss: ", "Last enc. boss: ")
        map_id = self._last_status.get("map_id", None)
        # Append map info
        if map_id in self.map_info.index:
            status += f" | Map: ({map_id}), {self.map_info.loc[map_id]['name']}"
        # Append party info
        party = [f"{name[1:-1]}: {alias}"
                 for name, alias in self._last_status.get("party", {}).items() if name.startswith("(")]
        if party:
            status += " | Party: " + ", ".join(party)
        # Append leaderboard
        leaderboard = " | ".join([f"{user}: {inv.get('score', None)}"
                                  for user, inv in sorted(self._user_data.items(),
                                                          key=lambda kv: -kv[1].get("score", 0))])

        logging.debug(f"Logging last 3 of {len(self._history)} events.")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        events = [f"({t}) {v}" for t, v in sorted(self._history.items(),
                                                  key=lambda kv: kv[0]) if v.startswith("!event")][-3:]
        last_3 = f"--- [{current_time}] Last three events:\n" + "\n".join(events)

        if os.path.exists("_scoring.txt"):
            with open("_scoring.txt", "r") as f:
                last_3 += "\n\n" + f.read()
            os.unlink("_scoring.txt")

        # truncate file
        with open(fname, "w") as f:
            print(status + "\n\n" + leaderboard + "\n\n" + last_3 + "\n", file=f, flush=True)

    #
    # User interaction
    #
    def _check_user(self, user):
        """
        Check if a user is already registered in the user database.

        :param user: (str) user
        :return: (bool) whether or not the user is in `_USERS`
        """
        return user in self._user_data

    def _sell_all(self):
        """
        Iterate through the user database and sell all salable items. Generally invoked at the end of a seed.

        :return: None
        """
        for user, inv in self._user_data.items():
            for cat, item in inv.items():
                # Omit categories that don't have salable items (e.g. score)
                if cat not in self._lookups:
                    continue
                try:
                    # We assume the user hasn't somehow managed to buy an item not in the lookup table
                    lookup, info = self._lookups[cat]
                    # Add the sale price back to the score
                    inv["score"] += int(info.set_index(lookup).loc[item]["Sell"])
                except Exception as e:
                    logging.error("Problem in sell_all:\n" + str(e) + "\nUser table:\n" + str(self._user_data))

            # Clear out the user selections, drop all categories which aren't the score
            self._user_data[user] = {k: max(v, 1000) for k, v in inv.items() if k == "score"}
            logging.info(f"Sold {user}'s items. Current score {self._user_data[user]['score']}")
        logging.info("Sold all users items.")

    #
    # Serialization and checkpointing
    #

    def serialize(self, pth="./", reset=False, archive=None, season_update=False):
        """
        Serialize (write to file) several of the vital bookkeeping structures attached to the bot.

        Optionally archive the entire information set to a directory (usually the seed).
        Optionally send checkpoint to trash and reset the bot state.
        Optionally update a season-tracking file with user scores.

        :param pth: path to checkpoint information to
        :param reset: whether or not to reset bot state (default is False)
        :param archive: path to archive the checkpoint (default is None)
        :param season_update: whether or not to update the season scores (default is False)
        :return: None
        """

        # Create the serialization directory if it doesn't already exist
        if not os.path.exists(pth):
            logging.info(f"Creating serialization path {pth}")
            os.makedirs(pth)

        # Save the current history to a JSON file in the serialization path
        logging.info(f"Serializing path {pth}/history.json")
        with open(os.path.join(pth, "../history.json"), "w") as fout:
            json.dump(self._history, fout, indent=2)

        # Save the current user data to a JSON file in the serialization path
        logging.info(f"Serializing path {pth}/user_data.json")
        with open(os.path.join(pth, "../user_data.json"), "w") as fout:
            json.dump(self._user_data, fout, indent=2)

        # Save the last know game status to a JSON file in the serialization path
        logging.info(f"Serializing path {pth}/_last_status.json")
        # If we're paused, we probably stopped the bot, so the frame counter should be zero
        # This is more of a debug check than anything
        if self._bot._status == "paused" and self._last_status.get("frame") != 0:
            logging.warning("Warning, the frame counter is not zero, but it *probably* should be.")
        with open(os.path.join(pth, "_last_status.json"), "w") as fout:
            json.dump(self._last_status, fout, indent=2)

        # The seed has likely ended one way or another, and the user has requested an archive
        # operation, probably for a season.
        if archive is not None:
            spath = os.path.join("../data/", archive)
            # Create the archive path if it doesn't already exist
            if not os.path.exists(spath):
                logging.info(f"Creating archive path {spath}")
                os.makedirs(spath)

            # Move the checkpoint path to the archive path
            logging.info(f"Archiving {pth} to {spath}")
            shutil.move(pth, spath + "/")

            # We also update the season tracker
            sfile = os.path.join("../data/", archive, "season.csv")
            if season_update:
                logging.info(f"Adding season tracking information to {sfile}")
                try:
                    # Convert the user data into rows of a CSV table
                    this_seed = pandas.DataFrame(self._user_data)
                    logging.debug(f"Users: {self._user_data},\nseed database: {this_seed.T}")
                    # Drop everything but the score (the other purchase information is extraneous)
                    this_seed = this_seed.T[["score"]].T
                    # We alias the score to a unique identifier for each seed
                    this_seed.index = [self._seed + "." + self._flags]
                except KeyError as e:
                    logging.error("Encountered error in serializing user scores to update season-long scores. "
                                  f"Current user table:\n{self._user_data}")
                    raise e

                if os.path.exists(sfile):
                    logging.info(f"Concatenating new table to {sfile}")
                    prev = pandas.read_csv(sfile).set_index("index")
                    logging.debug(f"Current season has {len(prev)} (possibly including totals) entries.")
                    # If the season CSV already exists, we concatenate this seed data to it
                    season = pandas.concat((prev, this_seed))
                else:
                    logging.info(f"Creating new table at {sfile}")
                    # Otherwise, we create a new table
                    season = this_seed

                if "Total" in season.index:
                    season.drop("Total", inplace=True)
                season.loc["Total"] = season.fillna(0).sum()
                # FIXME: We should convert this to JSON instead
                season.reset_index().to_csv(sfile, index=False)
                season.index.name = "Seed Number"
                logging.info("Synching season scores to Google sheet...")
                export_to_gsheet(season.reset_index())
                logging.info("...done")

        if reset:
            os.makedirs("TRASH")
            # Renames instead of deleting to make sure user data integrity is only minimally threatened
            # Mark the checkpoint directory as trash by naming it as such
            if os.path.exists(self.chkpt_dir):
                shutil.move(self.chkpt_dir, "TRASH")
            # Move the logfile into the trash too, just in case it needs to be restored
            if os.path.exists("TRASH/"):
                shutil.move("../logfile.txt", "TRASH/")

            # reset bot status
            self.reset()

    def read_context(self, ctx_file):
        if os.path.exists(ctx_file):
            with open(ctx_file, "r") as fin:
                context = json.load(fin)
            logging.debug(context)
            return context

        return self._CONTEXT.copy()

    def read_last_status(self, status_file):
        if os.path.exists(status_file):
            with open(status_file, "r") as fin:
                return json.load(fin)

        return {}

    def find_latest_user_data(self, pth):
        latest = sorted(glob.glob(pth),
                        key=lambda f: os.path.getmtime(f))

        if len(latest) == 0:
            logging.info("find_latest_user_data | No user data files found.")
            return {}

        with open(latest[-1], "r") as fin:
            users = json.load(fin)

        logging.debug(users)
        return users

    #
    # State manipulation
    #
    def reset(self):
        self._status = None
        self._last_state_drop = -1

    #
    # Scoring Tables
    #
    def load_game_data(self, pth="data/"):
        self.area_info = pandas.read_csv(os.path.join(pth, "bc_fantasy_data_areas.csv"))
        self.boss_info = pandas.read_csv(os.path.join(pth, "bc_fantasy_data_bosses.csv"))
        self.char_info = pandas.read_csv(os.path.join(pth, "bc_fantasy_data_chars.csv"))

        self.map_info = pandas.read_csv(os.path.join(pth, "map_ids.csv"))
        self.map_info["id"] = [int(n, 16) for n in self.map_info["id"]]
        self.map_info = self.map_info.set_index("id")

        # Given a category, what column should be used to look up a selection against which table
        self._lookups = {
            "area": ("Area", self.area_info),
            "char": ("Character", self.char_info),
            "boss": ("Boss", self.boss_info),
        }

    # Optional mappings derived from spoiler
    def load_from_spoiler(self, spoiler_log):
        if spoiler_log and os.path.isdir(spoiler_log):
            try:
                spoiler_log = glob.glob(os.path.join(spoiler_log, "*.txt"))[0]
            except IndexError:
                logging.warning(f"Directory of spoiler log is not valid, no spoiler texts found: {spoiler_log}")

        if spoiler_log and os.path.exists(spoiler_log):
            self.flags, self.seed, maps = read.read_spoiler(spoiler_log)
            mmaps, cmaps = maps
            self.music_info = pandas.DataFrame(mmaps).dropna()
            self.char_map = pandas.DataFrame(cmaps).dropna()
        else:
            logging.warning(f"Path to spoiler log is not valid and was not read: {spoiler_log}")