"""Test suite for command parsing.

Validates that each input is correctly classified to the expected command
with the expected arguments, without executing any side effects.
"""

import pytest

from hecko.commands import (
    greeting, quit_demo, timer, weather, time_cmd,
    reminder, grocery, music, math_cmd, sports, repeat,
)

_ALL_MODULES = [
    greeting, quit_demo, timer, weather, time_cmd,
    reminder, grocery, music, math_cmd, sports, repeat,
]


def best_parse(text):
    """Parse text against all modules, return the winning Parse or None."""
    parses = []
    for mod in _ALL_MODULES:
        p = mod.parse(text)
        if p is not None:
            p.module = mod
            parses.append(p)
    if not parses:
        return None
    parses.sort(key=lambda p: -p.score)
    return parses[0]


def module_name(p):
    """Get the short module name from a Parse."""
    if p is None or p.module is None:
        return None
    return p.module.__name__.split(".")[-1]


# ---- Test cases ----
# Each tuple: (input_text, expected_command, expected_args_subset)
# expected_args_subset is checked with dict subset matching (<=)

# -- Time --

class TestTimeCmd:
    def test_what_time(self):
        p = best_parse("what time is it")
        assert p.command == "get_time"

    def test_what_day(self):
        p = best_parse("what day is it")
        assert p.command == "get_day"

    def test_what_date(self):
        p = best_parse("what is the date")
        assert p.command == "get_date"

    def test_todays_date(self):
        p = best_parse("what's today's date")
        assert p.command == "get_date"

    def test_tell_me_time(self):
        p = best_parse("tell me the time")
        assert p.command == "get_time"


# -- Weather --

class TestWeather:
    def test_whats_weather(self):
        p = best_parse("what's the weather")
        assert p.command == "current_weather"

    def test_temperature(self):
        p = best_parse("what's the temperature")
        assert p.command == "current_weather"

    def test_forecast(self):
        p = best_parse("what's the forecast")
        assert p.command == "forecast"

    def test_rain(self):
        p = best_parse("is it going to rain")
        assert p.command == "rain_check"

    def test_tomorrow(self):
        p = best_parse("what's the weather tomorrow")
        assert p.command == "forecast"


# -- Greeting --

class TestGreeting:
    def test_hello(self):
        p = best_parse("hello")
        assert p.command == "greet"
        assert p.score == 1.0

    def test_hi(self):
        p = best_parse("hi")
        assert p.command == "greet"

    def test_good_morning(self):
        p = best_parse("good morning")
        assert p.command == "greet"

    def test_thank_you(self):
        p = best_parse("thank you")
        assert p.command == "respond_thanks"

    def test_thanks(self):
        p = best_parse("thanks")
        assert p.command == "respond_thanks"

    def test_goodbye(self):
        p = best_parse("goodbye")
        assert p.command == "respond_goodbye"

    def test_see_you_later(self):
        p = best_parse("see you later")
        assert p.command == "respond_goodbye"

    def test_im_done(self):
        p = best_parse("I'm done")
        assert p.command == "respond_goodbye"

    def test_thats_all(self):
        p = best_parse("that's all")
        assert p.command == "respond_goodbye"


# -- Quit --

class TestQuit:
    def test_quit_demo(self):
        p = best_parse("quit demo")
        assert p.command == "quit"
        assert p.score == 1.0

    def test_exit_demo(self):
        p = best_parse("exit demo")
        assert p.command == "quit"


# -- Repeat --

class TestRepeat:
    def test_say_that_again(self):
        p = best_parse("say that again")
        assert p.command == "repeat"

    def test_repeat_that(self):
        p = best_parse("repeat that")
        assert p.command == "repeat"

    def test_what_did_you_say(self):
        p = best_parse("what did you say")
        assert p.command == "repeat"

    def test_pardon(self):
        p = best_parse("pardon")
        assert p.command == "repeat"

    def test_didnt_catch_that(self):
        p = best_parse("I didn't catch that")
        assert p.command == "repeat"


# -- Timer --

class TestTimer:
    def test_set_5_min(self):
        p = best_parse("set a timer for 5 minutes")
        assert p.command == "set_timer"
        assert p.args["seconds"] == 300
        assert p.args["label"] == "5-minute"

    def test_set_30_sec(self):
        p = best_parse("set a 30 second timer")
        assert p.command == "set_timer"
        assert p.args["seconds"] == 30

    def test_set_one_hour(self):
        p = best_parse("set a timer for one hour")
        assert p.command == "set_timer"
        assert p.args["seconds"] == 3600

    def test_set_half_min(self):
        p = best_parse("set a timer for a minute and a half")
        assert p.command == "set_timer"
        assert p.args["seconds"] == 90

    def test_query(self):
        p = best_parse("how much time is left")
        assert p.command == "query_timers"

    def test_cancel_specific(self):
        p = best_parse("cancel the 5 minute timer")
        assert p.command == "cancel_timer"
        assert p.args["label"] == "5-minute"

    def test_cancel_all(self):
        p = best_parse("cancel all timers")
        assert p.command == "cancel_all_timers"


# -- Reminder --

class TestReminder:
    def test_set_reminder_at_time(self):
        p = best_parse("remind me to feed the cat at 3pm")
        assert p.command == "set_reminder"
        assert p.args["text"] == "feed the cat"
        assert p.args["time"].hour == 15

    def test_set_reminder_time_first(self):
        p = best_parse("remind me at 12:30 to call my mom")
        assert p.command == "set_reminder"
        assert "call" in p.args["text"]
        assert p.args["time"].minute == 30

    def test_query_reminders(self):
        p = best_parse("what reminders do I have")
        assert p.command == "query_reminders"

    def test_cancel_all_reminders(self):
        p = best_parse("cancel all reminders")
        assert p.command == "cancel_all_reminders"


# -- Grocery --

class TestGrocery:
    def test_add_ketchup(self):
        p = best_parse("add ketchup to the shopping list")
        assert p.command == "add_item"
        assert p.args["item_name"] == "ketchup"
        assert p.args["important"] is False

    def test_put_on_list(self):
        p = best_parse("put diet 7 up on the grocery list")
        assert p.command == "add_item"
        assert p.args["item_name"] == "diet 7 up"

    def test_remove(self):
        p = best_parse("remove soda from the shopping list")
        assert p.command == "remove_item"
        assert p.args["item_name"] == "soda"

    def test_take_off(self):
        p = best_parse("take cream of tartar off the grocery list")
        assert p.command == "remove_item"
        assert p.args["item_name"] == "cream of tartar"

    def test_check(self):
        p = best_parse("do I have eggs on the shopping list?")
        assert p.command == "check_item"
        assert p.args["item_name"] == "eggs"

    def test_count(self):
        p = best_parse("how many items are on my grocery list?")
        assert p.command == "count_items"

    def test_important(self):
        p = best_parse("add butter to the shopping list and mark it important")
        assert p.command == "add_item"
        assert p.args["item_name"] == "butter"
        assert p.args["important"] is True

    def test_og_prefix_add(self):
        p = best_parse("tell Our Groceries to add cranberry juice")
        assert p.command == "add_item"
        assert p.args["item_name"] == "cranberry juice"

    def test_og_prefix_remove(self):
        p = best_parse("ask Our Groceries to remove milk")
        assert p.command == "remove_item"
        assert p.args["item_name"] == "milk"

    def test_og_prefix_important(self):
        p = best_parse("tell Our Groceries to add eggs and mark it important")
        assert p.command == "add_item"
        assert p.args["item_name"] == "eggs"
        assert p.args["important"] is True

    def test_whats_on_list(self):
        p = best_parse("what's on the shopping list")
        assert p.command == "count_items"


# -- Music --

class TestMusic:
    def test_play_some_music(self):
        p = best_parse("play some music")
        assert p.command == "play_music"

    def test_lets_have_music(self):
        p = best_parse("let's have some music")
        assert p.command == "play_music"

    def test_play_playlist(self):
        p = best_parse("play my Birthday Favorites playlist")
        assert p.command == "play_playlist"
        assert p.args["name"] == "Birthday Favorites"

    def test_play_track(self):
        p = best_parse("play Pour Some Sugar on Me")
        assert p.command == "play_track"
        assert p.args["title"] == "Pour Some Sugar on Me"

    def test_play_track_by_artist(self):
        p = best_parse("play Ordinary by Alex Warren")
        assert p.command == "play_track"
        assert p.args["title"] == "Ordinary"
        assert p.args["artist"] == "Alex Warren"

    def test_pause(self):
        p = best_parse("pause the music")
        assert p.command == "pause"

    def test_resume(self):
        p = best_parse("resume music")
        assert p.command == "resume"

    def test_stop(self):
        p = best_parse("stop the music")
        assert p.command == "stop"

    def test_skip(self):
        p = best_parse("skip song")
        assert p.command == "skip"

    def test_next_song(self):
        p = best_parse("next song")
        assert p.command == "skip"

    def test_whats_playing(self):
        p = best_parse("what's playing")
        assert p.command == "now_playing"

    def test_music_please(self):
        p = best_parse("music, please")
        assert p.command == "play_music"


# -- Math --

class TestMath:
    def test_times(self):
        p = best_parse("what's 347 times 23")
        assert p.command == "binary_op"
        assert p.args["a"] == 347.0
        assert p.args["b"] == 23.0
        assert p.args["op"] == "*"

    def test_plus(self):
        p = best_parse("what's 5 plus 3")
        assert p.command == "binary_op"
        assert p.args["a"] == 5.0
        assert p.args["b"] == 3.0
        assert p.args["op"] == "+"

    def test_minus(self):
        p = best_parse("what's 100 minus 37")
        assert p.command == "binary_op"
        assert p.args["a"] == 100.0
        assert p.args["b"] == 37.0

    def test_divided_by(self):
        p = best_parse("what is 144 divided by 12")
        assert p.command == "binary_op"
        assert p.args["op"] == "/"

    def test_percent_symbol(self):
        p = best_parse("what is 15% of 85")
        assert p.command == "percent"
        assert p.args["pct"] == 15.0
        assert p.args["base"] == 85.0

    def test_percent_word(self):
        p = best_parse("what's 15 percent of 200")
        assert p.command == "percent"
        assert p.args["pct"] == 15.0

    def test_square_root(self):
        p = best_parse("what's the square root of 144")
        assert p.command == "sqrt"
        assert p.args["n"] == 144.0

    def test_squared(self):
        p = best_parse("what is 7 squared")
        assert p.command == "power"
        assert p.args["n"] == 7.0
        assert p.args["exp"] == 2

    def test_cubed(self):
        p = best_parse("what's 3 cubed")
        assert p.command == "power"
        assert p.args["n"] == 3.0
        assert p.args["exp"] == 3

    def test_to_the_power_of(self):
        p = best_parse("what is 2 to the power of 8")
        assert p.command == "binary_op"
        assert p.args["op"] == "**"


# -- Unit Conversion --

class TestUnitConversion:
    def test_tablespoons_in_quarter_cup(self):
        p = best_parse("how many tablespoons in a quarter cup")
        assert p.command == "convert_units"
        assert p.args["value"] == 0.25
        assert p.args["from_unit"] == "cup"
        assert p.args["to_unit"] == "tablespoon"

    def test_feet_in_mile(self):
        p = best_parse("how many feet in a mile")
        assert p.command == "convert_units"
        assert p.args["from_unit"] == "mile"
        assert p.args["to_unit"] == "foot"

    def test_convert_temp(self):
        p = best_parse("convert 72 fahrenheit to celsius")
        assert p.command == "convert_units"
        assert p.args["value"] == 72.0
        assert p.args["from_unit"] == "degF"
        assert p.args["to_unit"] == "degC"

    def test_whats_in(self):
        p = best_parse("what's 5 feet in centimeters")
        assert p.command == "convert_units"
        assert p.args["value"] == 5.0

    def test_cups_in_half_gallon(self):
        p = best_parse("how many cups in a half gallon")
        assert p.command == "convert_units"
        assert p.args["value"] == 0.5
        assert p.args["from_unit"] == "gallon"

    def test_three_quarters_cup(self):
        p = best_parse("how many tablespoons in three quarters cup")
        assert p.command == "convert_units"
        assert p.args["value"] == 0.75


# -- Sports --

class TestSports:
    def test_next_game_team(self):
        p = best_parse("when's the next U of A basketball game")
        assert p.command == "next_game"
        assert len(p.args["teams"]) >= 1

    def test_next_game_wildcats(self):
        p = best_parse("when's the next wildcats game")
        assert p.command == "next_game"

    def test_this_week(self):
        p = best_parse("is there a basketball game this week")
        assert p.command == "this_week"

    def test_next_week(self):
        p = best_parse("any games next week")
        assert p.command == "next_week"

    def test_last_game(self):
        p = best_parse("who won the last Arizona game")
        assert p.command == "last_game"

    def test_score(self):
        p = best_parse("what was the score of the last basketball game")
        assert p.command == "last_game"

    def test_how_did_cats_do(self):
        p = best_parse("how did the cats do")
        assert p.command == "last_game"

    def test_generic_game(self):
        p = best_parse("when's the next game")
        assert p.command == "next_game"


# -- No match --

class TestNoMatch:
    def test_nonsense(self):
        p = best_parse("flurble garble zoop")
        assert p is None

    def test_random_sentence(self):
        p = best_parse("the cat sat on the mat")
        assert p is None


# -- Module routing (ensure right module wins) --

class TestRouting:
    def test_time_not_timer(self):
        """'what time is it' should go to time_cmd, not timer."""
        p = best_parse("what time is it")
        assert module_name(p) == "time_cmd"

    def test_weather_not_greeting(self):
        """Weather queries should beat greeting even if 'good' is in text."""
        p = best_parse("what's the weather")
        assert module_name(p) == "weather"

    def test_repeat_beats_others(self):
        """Repeat commands score 0.95, should beat most things."""
        p = best_parse("say that again")
        assert module_name(p) == "repeat"
