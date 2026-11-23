"""Typed task actions and replies (command/typed.py). ACTIONS: sentence -> (action, task id or None, args subset)."""

ACTIONS = {
    "done": [
        "done", "done!", "finished it", "i did the reading", "mark lab 7 done", "knocked it out", "i'm done", "im done w it", "all done", "did it",
        "just finished", "nailed it", "complete read chapter 5", "mark read chapter 5 as complete", "i finished lab 7", "finished the week 4 discussion",
        "check off lab 7", "lab 7 is done", "read chapter 5 is finished", "i just finished the reading", "ok done", "yeah done", "finished that up",
        "that's done", "cross it off", "mark it done pls", "can you mark lab 7 done", "i wrapped up read chapter 5", "got that done",
    ],
    "start": [
        "start", "let's go", "starting now", "begin", "lets start", "i'm starting", "start the timer", "starting lab 7", "begin read chapter 5",
        "start working on lab 7", "let's do lab 7", "i'll start the week 4 discussion", "ok start", "ready", "go time", "start the block", "time to start",
        "can you start the timer", "start network traffic analyzer", "start working",
    ],
    "started_earlier": [
        "i started 20 min ago", "started 15 minutes ago", "i started an hour ago", "i started it about 30 mins ago", "i've been working on it for 25 minutes",
        "i started lab 7 40 min ago", "forgot to start, started 10 min ago", "i started half an hour ago", "been at it for 45 minutes", "started 5 mins ago lol",
    ],
    "snooze": [
        "snooze", "later", "not now", "snooze for an hour", "snooze this for 2 hours", "remind me in 2 hours", "push it to tomorrow", "snooze lab 7 till 5pm",
        "snooze until tomorrow", "not right now", "maybe later", "can't right now", "snooze it", "snooze for 30 min", "ask me again in an hour",
        "remind me about it in 3 hours", "push lab 7 to friday", "snooze read chapter 5 for an hour", "put it off till tomorrow", "come back to this later",
        "bump it to tomorrow", "snooze 3 hours", "snooze till tonight", "postpone it until friday", "delay this for a couple hours", "remind me later",
    ],
    "skip": [
        "skip", "skip it", "skip this one", "not this one", "give me something else", "something else", "i don't want to do this", "i dont wanna do this one",
        "skip lab 7", "show me something else", "swap it", "pick something else", "not lab 7", "next one please", "another one", "different one",
    ],
    "pin": [
        "pin", "pin this", "pin it", "pin lab 7", "do this first today", "keep this on top", "do lab 7 first", "make this my top priority", "move lab 7 to the top",
        "put this at the top", "focus on lab 7 today", "make read chapter 5 the priority", "do this one first",
    ],
    "unpin": ["unpin", "unpin it", "unpin this", "unpin lab 7", "take it off the top", "stop pinning this", "unpin everything", "remove the pin"],
    "stuck": ["i'm stuck", "im stuck on lab 7", "stuck on read chapter 5", "help me start lab 7", "i can't get started", "overwhelmed", "i have no idea where to start"],
    "add_time": [
        "add 15 minutes", "add 15 min", "give me 15 more minutes", "15 more minutes", "i need 15 more minutes", "5 more minutes", "plus 15", "another 15 minutes",
        "more time", "add some time", "extend it by 20 minutes", "add an hour", "extend the block", "give me 10 more mins", "need 30 more minutes",
    ],
    "break": ["take a break", "break", "i need a break", "break time", "lets take a break", "time for a break", "i'm taking a break", "pause", "stop here", "i need a breather", "need a quick break", "gonna take a break"],
    "end_break": ["end break", "end the break", "break's over", "break is over", "im back", "back to work", "i'm done with my break", "finished my break", "ready to work again", "stop the break"],
    "skip_break": ["skip the break", "no break", "skip break", "i don't need a break", "no break needed"],
    "cancel_block": ["cancel the block", "cancel block", "stop the block", "end the block", "abort the block", "cancel the timer", "scrap the block", "end the session", "kill the timer"],
    "low_energy_on": ["i'm tired", "im tired", "low energy", "low energy mode", "turn on low energy", "im exhausted", "i'm drained", "not feeling it today", "rough day", "i have no energy", "take it easy today", "go easy on me", "im wiped", "i feel sick", "no energy today"],
    "low_energy_off": ["im good now", "i'm feeling better", "i feel better", "turn off low energy", "low energy off", "back to normal", "my energy's back", "normal mode", "i have energy now"],
    "undo": ["undo", "undo that", "take that back", "oops undo", "never mind that", "revert that", "put it back", "reopen it", "scratch that", "i didn't mean to", "whoops"],
}

# Task ids (see phrasings.TASKS): "lab 7" -> t2, "read chapter 5" -> t1, "week 4 discussion" -> t5, "network traffic analyzer" -> t3
TASK_OF = {"lab 7": "t2", "read chapter 5": "t1", "week 4 discussion": "t5", "network traffic analyzer": "t3"}

NOT_ACTIONS = [
    "should i snooze this?", "what did i finish today", "did i finish lab 7?", "how do i start a venv", "can i skip this?", "is lab 7 done?", "when did i start",
    "what should i do next", "snooze button not working", "how do i pin something", "go to the gym three times a week", "start a new react project",
    "i did the dishes and need a new plan", "when is my break", "what's a good break length", "should i take a break?", "do i have time to start lab 7",
    "stop procrastinating tips", "pass the salt recipe ideas", "undo button ideas for my app", "i finished the dishes", "write a cover letter for acme",
    "explain what a snooze alarm does", "what happens if i skip a task", "why is it taking so long", "i'm done with that guy", "my break was great",
    "the block is on my calendar", "remind me to call mom in 2 hours", "remind me in 2 hours to stretch", "later gator", "i started a new job 2 weeks ago",
    "wait, skip this?", "oh, snooze this?", "hmm, pin this?", "ok so done?",
    "i'm tired of this lab and want a better explanation", "what's low energy mode", "how do i add 15 minutes to a block", "what pin does", "can you explain pinning",
]

# pending add: title, list, due; replies and the dict each should give. Written before the code was run.
PENDING = {"type": "add", "title": "Email Dr. Lee about the lab", "list": "Network Security", "due": "2026-11-13T12:00-05:00", "mode": "task",
           "lists": ["Cloud Computing", "Network Security", "Internships", "Security Projects", "Personal", "Play", "General"]}

YES = ["yes", "yep", "sure", "do it", "add it", "ok", "sounds good", "yeah", "yup", "yes please", "go ahead", "looks good", "that's right", "okay", "k", "perfect", "yes add it", "sure thing", "ya", "for sure", "yea add it"]
NO = ["no", "nah", "cancel", "don't", "nope", "never mind", "nvm", "forget it", "no thanks", "dont add it", "scratch that", "changed my mind", "nope cancel", "stop"]
NOT_TASK = ["not a task", "that's not a task", "it's a question", "just a question", "i was asking", "thats a question"]
EDITS = [
    ("make it saturday", {"due": "2026-11-14"}), ("friday at 3", {"due": "2026-11-13T15:00"}), ("tomorrow", {"due": "2026-11-11"}),
    ("put it in school", {"listHint": "school"}), ("personal not school", {"list": "Personal"}), ("make it personal", {"list": "Personal"}),
    ("move it to internships", {"list": "Internships"}), ("in cloud", {"list": "Cloud Computing"}),
    ("call it email Dr. Lee about the quiz", {"title": "email Dr. Lee about the quiz"}),
    ("rename it to Call the dentist", {"title": "Call the dentist"}),
    ("no date", {"clearDue": True}), ("no due date", {"clearDue": True}), ("without a date", {"clearDue": True}),
    ("text me instead", {"mode": "reminder"}), ("just text me", {"mode": "reminder"}), ("make it a text", {"mode": "reminder"}),
    ("also text me", {"alsoText": True}), ("just a task", {"mode": "task"}), ("no texts", {"mode": "task"}),
    ("change it to monday", {"due": "2026-11-16"}), ("due friday", {"due": "2026-11-13"}), ("by sunday", {"due": "2026-11-15"}),
    ("5pm", {}), ("how about friday", {"due": "2026-11-13"}), ("put it in network security", {"list": "Network Security"}),
    ("it's a security project", {"list": "Security Projects"}), ("file it under play", {"list": "Play"}),
    ("in 2 hours", {}), ("friday in personal", {"due": "2026-11-13", "list": "Personal"}), ("move it to next friday", {}),
]
NOT_REPLIES = [
    "what's due friday", "remind me to call mom tomorrow", "what should i do now", "what is the due date", "should it be friday?", "where did i leave off",
    "find my resume", "explain tcp", "i'm stuck on lab 7", "call mom", "email the recruiter back", "how's the analyzer going",
]
