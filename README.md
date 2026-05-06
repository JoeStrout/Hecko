**Hecko** is a **home-grown replacement for Amazon Echo**.  It's a voice-interface assistant that can handle:

  - **Greetings** — hello, good morning, thank you, goodbye, etc.                                                 
  - **Timers** — set, query, and cancel multiple named timers                                                     
  - **Reminders** — set reminders at a specific time; fires with a chime and announcement                         
  - **Weather** — current conditions, 3-day forecast, rain check (Tucson, via Open-Meteo)                         
  - **Time/date** — current time, day of week, or full date                                                       
  - **Location** — find family members' devices via iCloud Find My                                                
  - **Grocery list** — add, remove, check, and count items on Our Groceries                                       
  - **Music** — Spotify playback control (play, pause, playlists, liked songs, volume duck/restore)               
  - **Ask Claude** — forward open-ended questions to the Anthropic API                                            
  - **Math/conversions** — arithmetic and unit conversions (via pint)                                             
  - **Sports** — upcoming games and recent results for followed teams (ESPN API)                                  
  - **Stock prices** — current price and historical comparison via Yahoo Finance                                  
  - **Repeat** — repeat the last spoken response                                                                  
  - **Sleep/wake** — pause and resume listening (for privacy)

Hecko was developed as a 2-week project, while stuck in a rental unit with no access to our home Echo.  
I'd been meaning to wean our household off of Alexa for a while anyway, and that stay while our floors
were being remodeled was just the push I needed.

Hecko now surpasses the feature set that we use our Echo for, which is mostly timers, alarms, music, and groceries.
Hecko can do these and much more; and some things that both can do, Hecko does better.  For example,
instead of "tell Our Groceries to add milk", we can now say "add milk to the grocery list", and several other
natural variations.

Hecko works reasonably well with my MacBook Pro's built-in speaker and
microphone, but even better with a USB conference speaker.

Hecko is written in Python, and was mostly written by Claude under my direction.  It features extensive
unit tests, particularly when it comes to parsing commands.  It makes use of deep neural networks for
speech recognition and synthesis, but does _not_ use an LLM for conversation (unless you explicitly tell
it to "ask Claude" something).  So, parsing is based on simple command patterns, just like Amazon Alexa.

Hecko was built for my own needs, and not really intended to be easily usable by others — but the code is
all under the liberal [MIT License](LICENSE), so if you want to try, have fun!
