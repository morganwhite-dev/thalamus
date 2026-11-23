"""Held-out sentences for judging the meaning matcher (command/matcher_eval.py).

Written blind, in texting style, BEFORE looking at the example tables, then de-duplicated against them
(see overlap_report() at the bottom). Keep these out of the example tables: if a sentence is copied there, it stops being a test.

Labels: now, schedule, capture, park, project, lookup, reminders, stuck, action, tiny, general, noact.
"""

HELDOUT = {
    "now": [
        "ok so what am i supposed to be doing", "yo which thing do i hit first", "idk where to begin today, help",
        "whats on deck for me rn", "just assign me something lol", "what is the move right now", "what do i work on after this",
        "ok brain pick something for me", "so whats the priority", "what should my next hour look like",
        "im sitting down now, what first", "hand me the next thing", "what am i meant to be on rn", "which thing first",
        "what am i on right now", "whats after this for me", "need direction, what do i do", "what should i be grinding on",
        "so what's the plan rn", "tell me what to start", "what do i do with the next 45 minutes", "whatcha got for me",
        "what's the most important thing for me rn", "ok what now lol", "which task should i take on", "what's my focus right now",
    ],
    "schedule": [
        "anything due tmrw", "anything i gotta hand in by friday", "do i have stuff due this weekend", "whats overdue", "how stacked is my deadline list this week",
        "any quizzes coming up", "how does the week ahead shape up", "when's the next thing due", "got anything to submit today",
        "what assignments are left for cloud", "show me whats due next week", "what do i have to turn in soon",
        "what's due monday", "got any deadlines tonight", "how busy is this week", "what's late rn", "when is my next test",
        "what's due for network security this week", "stuff to turn in before sat", "list my upcoming deadlines",
        "which assignments are due thursday", "what's left for internships this week", "do i have a lab due soon",
        "what deadlines am i behind on", "when's the midterm", "whats coming at me this week",
    ],
    "capture": [
        "gotta buy a birthday gift for my sister", "need to get my car inspected", "put 'call the bank' on my list",
        "add dentist appointment thursday", "i have to turn in my parking form", "dont let me forget to pay my phone bill",
        "need to email my advisor about registration", "add grocery run tmrw", "remind me to water the plants sunday",
        "todo: renew my license", "i should book flights for spring break", "add take out trash",
        "i need to print my boarding pass", "make a task for filing my taxes", "gonna need to pick up a package friday",
        "remind me to submit the form by wednesday", "add oil change to errands", "i have to return those shoes",
        "text me tomorrow at 5 to go to the gym", "put finish the slides on my list for thursday", "remember to cancel my free trial",
        "add a task: sign the lease", "need to refill my prescription this week", "i gotta schedule a haircut",
        "i need to apply to the google internship by sunday", "reminder to myself: back up my laptop",
    ],
    "park": [
        "random idea: a discord bot that quizzes me on ports", "idea for later: a tool that tracks my golf swings",
        "save this idea: browser extension that blocks doomscrolling", "park it: lil app that rates my commit messages",
        "put this in the parking lot: a honeypot for my home network", "new idea: dashboard for my steam backlog",
        "i thought of something cool, a game where you hack a toaster", "jot down this idea, password manager in rust",
        "stash this thought: cli that summarizes man pages", "idea: a script that renames my screenshots",
        "parking lot: voice controlled todo list", "side idea: a visualizer for dns traffic", "store this idea for later: wordle but for cve ids",
        "just had an idea for a recipe app", "shower thought: an app that nags me to touch grass", "park this one: tiny game engine in python",
        "write down my idea about a flashcard game", "idea dump: a plugin that colors my terminal by risk", "save for later: a bot to track internship postings",
        "i wanna remember this idea: sandbox for malware demos", "park: make a wiki for my notes", "a cool project idea just hit me, a log parser",
        "add to ideas: smart mirror that shows my schedule", "put an idea in the lot, ai that critiques my resume",
    ],
    "project": [
        "where'd i leave off on the traffic analyzer", "how close is the analyzer to done", "what was the last thing i did on the analyzer",
        "remind me where i stopped on my project", "status on the network analyzer?", "whats the latest on my security project",
        "when did i last touch the analyzer", "catch me up on where the project is at", "how's my project coming along",
        "where did i stop with the analyzer", "what did i get done on the project last time", "pick up where i left off on the analyzer",
        "fill me in on the analyzer", "what's the state of the traffic analyzer", "how much have i done on my portfolio project",
        "last time on the analyzer what happened", "what was i in the middle of", "where am i at with the detection pipeline",
        "refresh me on the analyzer", "what's the status of my side project", "which part of the analyzer was i working on",
        "give me a recap of the project", "refresh the analyzer status line", "is the analyzer done yet or what",
    ],
    "lookup": [
        "can u find my lecture slides for week 3", "where did i put the syllabus", "i need the cloud notes from module 5",
        "open my resume pdf", "find the study guide for network sec", "where's that lab 4 doc", "do i have notes for module 7",
        "pull up the ec council lab file", "dig up my cover letter for chase", "where are my teaching notes for week 6",
        "get the midterm review sheet", "show me the module 2 slides", "is there a quiz file for module 3",
        "locate the aws lab instructions", "open the planner file", "got the slides from the first week anywhere",
        "find that pdf about firewalls", "where did the cloud study guide go", "need the assignment doc for lab 9",
        "search my files for the syllabus", "open module 8 notes", "can you get me the network security syllabus",
        "do you have the exam review for cloud", "i'm looking for my tailored resume for deloitte",
    ],
    "reminders": [
        "what nudges are queued up for me", "which texts are lined up", "list all my scheduled texts", "pull up my reminder list",
        "nix the dentist text", "get rid of the reminder about the rent", "stop texting me about stretching",
        "what pings are set for tomorrow", "any reminders for tonight", "kill all my reminders", "delete the text about the gym",
        "how many texts are scheduled", "what am i going to get texted about", "remove the reminder for laundry",
        "which reminders are active", "what's pending in my texts", "turn off the water reminder", "view my scheduled reminders",
        "wipe all my follow ups", "show me every text queued up", "i dont want the call mom reminder anymore",
        "check what texts are coming today", "are there any texts lined up for later", "clear the reminder i made for friday",
    ],
    "stuck": [
        "i have no clue how to start lab 7", "stuck on this discussion post", "ugh cant get going on the reading", "im blanking on how to begin",
        "give me a tiny first step for the analyzer", "this lab is too big i dont know where to start", "cant make myself start",
        "what's the smallest thing i can do on this", "im overwhelmed by chapter 6", "help i keep staring at the blank doc",
        "how do i even begin this assignment", "stuck, chop this up into tiny bits", "i froze up on the project", "give me a 5 minute start",
        "paralyzed rn, what's step one", "cant figure out where to begin with the cloud lab", "so lost on this one, first step?",
        "im avoiding this and need a nudge to start", "just tell me the first thing to do for lab 9", "need help getting started on the essay",
        "brain wont let me start", "what do i do first on the quiz prep", "i dont know how to tackle this", "start me off on the midterm review",
    ],
    "action": [
        "ok finished it", "yup that one's done", "lab 7 complete", "skip it for now", "hold off on that for an hour", "bump it till tmrw",
        "reading is finished", "pause on this one", "begin the timer", "gonna start now", "pin the analyzer to the top",
        "not this one, next", "extend it by fifteen", "i'm wiped, low energy mode on", "take a break now", "scrap this work block",
        "marking read chapter 5 as finished", "done w the discussion", "fried, go easy on me mode", "end my break",
        "snooze for 3 hours", "kick off lab 7", "wrapped that up lol", "cross lab 7 off", "unpin that",
        "stop this block", "lets get going", "yea thats finished",
    ],
    "tiny": [
        "kkk", "ty", "haha", "yeahh", "tysm", "hmm", "ohh ok", "nice", "gotcha", "aight", "bet", "np", "yepp", "naw",
        "heyy", "ayy", "whats good", "alright cheers", "halp", "wut", "huh", "oh", "morning!", "yesss", "4", "noo",
    ],
    "general": [
        "what is a buffer overflow", "explain how tcp handshakes work", "write me a haiku about monday", "python way to flip a string?",
        "whats the difference between symmetric and asymmetric encryption", "give me 5 ideas for a cybersecurity portfolio project",
        "help me write a thank you email to a recruiter", "why is my python script throwing a keyerror", "summarize the cia triad",
        "what should i wear to an interview", "how many calories in an avocado", "recommend a good podcast about hacking",
        "can you explain what a vpc is", "draft a linkedin message to a hiring manager", "how many pages is a normal cover letter",
        "what's a good golf drill for slicing", "translate good luck into spanish", "write a regex that matches phone numbers",
        "whats the best way to study for a security cert", "explain docker like im five", "css trick to put a box in the middle",
        "is it better to take the internship or do research", "fix this sql query for me", "idempotent meaning in plain english",
        "give me interview questions for a cloud security job", "tell me a joke about firewalls",
    ],
    "noact": [
        "should i skip lab 7?", "is it ok to snooze this", "what happens when i hit done", "did i already start the analyzer",
        "how long did i work today", "can i pin two things", "why would i pause a block", "what if i didn't finish the reading",
        "the discussion post is done being graded", "i skipped breakfast", "my phone was on snooze all morning",
        "the timer app on my phone is broken", "i started at a new gym", "paused my netflix lol", "how do i finish a sentence in spanish",
        "what's the best way to complete a degree faster", "did my professor start the quiz yet", "he finished the race in 3 hours",
        "is the lab done being posted", "pin the tail on the donkey is a dumb game", "do i have to finish lab 7 tonight",
        "my low energy is killing me today", "someone pinned my tweet", "tell me about skipping stones",
        "why do i keep snoozing my alarm", "when does the break end", "do you think i should take a break",
        "i cant tell if the block is on", "everything is done and dusted at my old job",
    ],
}

# Questions and statements that must never come back as `action` or `capture` (or be created as tasks).
MUST_NOT_ACT = [
    "should i push this back?", "wake me at 7am", "i had some idea about the outage", "what if i skipped class", "did i finish the lab?",
    "the lab was done badly lol", "do i need to finish lab 7?", "would it be bad to skip the discussion", "what time does the quiz start",
    "i have a dentist appointment", "my mom needs to buy a gift", "he said he'd pay the rent", "you should remind me less",
    "is it smart to start now?", "how do i add a task in quicktodo", "did you add the lab to my list", "who needs to submit the form",
    "i forgot to eat today", "i need a vacation", "what is a todo list", "should i add an alarm", "i might apply to deloitte someday",
    "she had to return the shoes", "why is the due date different", "is the form due friday?", "i thought of pizza for dinner",
    "he's gonna pick up the package", "my idea was bad lol", "was the lab start time moved?", "i'm done lol this class is hard",
    "i started the semester behind", "what does the pin button do", "if i skip this does it come back", "do not disturb is on",
    "the reminder app crashed again", "no idea what to do tonight", "my friend has to cancel his trial", "how many times can i snooze",
    "whats the point of a break", "i am so stuck in traffic",
]


def _norm(s):
    return " ".join("".join(c if c.isalnum() else " " for c in s.lower()).split())


def overlap_report(examples_by_label):
    """Held-out sentences that are exact or near copies (token Jaccard >= 0.8) of any example. Returns [(label, sentence, example)]."""
    ex = [(l, e, set(_norm(e).split())) for l, es in examples_by_label.items() for e in es]
    out = []
    for label, sents in list(HELDOUT.items()) + [("MUST_NOT_ACT", MUST_NOT_ACT)]:
        for s in sents:
            ts = set(_norm(s).split())
            for l, e, te in ex:
                if ts and te and len(ts & te) / len(ts | te) >= 0.8:
                    out.append((label, s, e))
                    break
    return out
