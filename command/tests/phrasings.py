"""Plain sentences Morgan might type, with the handler that should take each one (see command/route_preview.py).
"free" = answered by a free model with no classifier call; nothing in this file should need a paid model to route."""

TASKS = [
    {"id": "t1", "title": "Read Chapter 5", "list": "Network Security"},
    {"id": "t2", "title": "Lab 7 - Construct Native FGSM and PGD Attacks on Image Classifiers using TensorFlow", "list": "Network Security"},
    {"id": "t3", "title": "Network traffic analyzer", "list": "Security Projects"},
    {"id": "t4", "title": "Apply to 10 internships (week of Nov 2)", "list": "Internships"},
    {"id": "t5", "title": "Week 4 Discussion", "list": "Network Security"},
    {"id": "t6", "title": "Finish paypal hackathon project", "list": "Personal"},
]

CASES = {
    # ---- "what should I be doing": the priority engine, no model
    "now": [
        "what should i do now", "what should I be doing right now?", "what should i do", "what should i work on",
        "what do i do now", "what do i do next", "whats next", "what's next?", "what next", "now what", "ok now what",
        "what should i be doing", "what do i need to do today", "what do i need to do", "where should i start",
        "where do i start", "what should i start with", "what should i start on", "what's the plan", "whats the plan for today",
        "what am i doing today", "what's first", "what should i focus on", "what's my next task", "whats my next thing",
        "give me something to do", "what's the most important thing right now", "what should i tackle first",
        "i dont know what to do", "i don't know what to work on", "what do i work on", "whats up next", "what's my top priority",
        "what's the priority", "tell me what to do", "what should i do first", "ok im done what now", "i finished, whats next",
        "what should i prioritize", "what should i prioritize today", "should i do the lab or the reading first",
        "which should i do first", "what comes next", "next task", "what's my priority today", "what do you want me to do",
        "what am i supposed to be doing", "what needs doing", "what needs to get done today", "what can i knock out right now",
        "plan my day", "what's on deck", "hit me", "what now?", "next", "what's the move", "what do i tackle next",
    ],
    # ---- what is due / left / overdue / how loaded: plain code from the snapshot
    "schedule": [
        "what's due today", "whats due tmrw", "what is due this week", "anything due tomorrow", "do i have anything due friday",
        "what do i have due this week", "what assignments are due", "is anything overdue", "am i behind", "am i behind on anything",
        "what did i miss", "how many assignments do i have left", "what's left for network security", "what homework do i have",
        "do i have homework", "whats coming up", "what's coming up this week", "what does my week look like", "what's my week look like",
        "when is my next deadline", "what's overdue in cloud", "what do i have left for internships", "what's due friday",
        "whats due next week in network security", "how many things are due this week", "what's on my plate", "what's on my plate this week",
        "anything due tonight", "is there anything due this weekend", "what do i have to turn in this week", "show me what's due",
        "list everything due this week", "what's due tmr", "what's due 2morrow", "do i have any deadlines this week",
        "what do i owe this week", "when is lab 7 due", "when's the week 4 discussion due", "is read chapter 5 overdue",
        "what's due for school", "any tests this week", "do i have a quiz this week", "how much do i have left this week",
        "what's still open", "what haven't i done", "what have i not finished",
        "do i have class today", "when is my next class", "when is the midterm", "what time is class tonight", "is there class tomorrow",
        "summarize my week", "what should i do tomorrow", "what should i do this weekend", "what do i have friday", "recap my week",
    ],
    # ---- add a task / reminder / repeating item: the confirm card
    "capture": [
        "remind me to call mom tomorrow", "i need to email dr lee friday", "add buy milk", "gotta renew my id",
        "dont forget to submit lab 7", "don't forget to pay rent", "can you add finish resume to my list", "could you remind me to call the dentist",
        "please remind me to email dr lee", "add a task to renew my parking pass", "new task: order textbooks", "task: call the bank",
        "i should call the dentist", "need to pay rent by friday", "have to finish chapter 5 tonight", "set a reminder for 5pm to stretch",
        "remind me at 5pm to stretch", "text me at 9am to take my meds", "put golf with sam on saturday", "schedule dentist for next tuesday",
        "call mom", "email professor lee", "buy groceries", "pay the electric bill", "book a tee time for saturday",
        "do tryhackme for one hour a day", "practice python every weekday", "go to the gym three times a week", "do giannas bday python project",
        "i wanna go golfing saturday", "i want to start the cloud lab tomorrow", "remember to bring my laptop charger", "remember to email the recruiter",
        "can you remind me to submit the lab tonight", "would you add pick up dry cleaning", "todo call the registrar", "note to self: renew passport",
        "add finish paypal slides to personal", "add study for midterm to network security due thursday", "i need to finish the paypal hackathon project by nov 27",
        "make sure i email the recruiter back", "make sure i submit lab 8 by wednesday", "i gotta do laundry tonight", "ill need to print my resume tomorrow",
        "set a reminder to call mom at 6pm", "remind me in 20 minutes to check the oven", "ping me at 3pm about the meeting",
        "sign up for the career fair", "register for spring classes", "cancel my gym membership", "return the amazon package",
    ],
    "park": [
        "idea: build a retro game launcher", "park this idea: a cli for my planner", "i have an idea for a discord bot",
        "put a recipe app in the parking lot", "park a habit tracker for golf", "random idea: wifi heatmap of my apartment",
        "i just had an idea for a packet sniffer game", "new idea: resume keyword matcher", "side project idea: ctf writeup site",
        "thought: make a browser extension for handshake", "idea - automate my lab reports",
    ],
    "project": [
        "where was i", "where did i leave off", "where am i on the analyzer", "how's the analyzer going", "status of analyzer",
        "what's the status on the network traffic analyzer", "what was i doing on the analyzer", "catch me up on the analyzer",
        "remind me where i was on the analyzer", "remind me where i left off", "what did i do last on the analyzer", "pick up where i left off",
        "where'd i leave off", "where did i stop on the analyzer", "update the status of the analyzer", "what was i working on",
        "what was i last doing", "where were we", "hows the network analyzer coming along", "what's the latest on the analyzer",
        "progress on the analyzer", "where am i at with the analyzer",
    ],
    "lookup": [
        "find my resume", "where's my resume", "wheres my resume", "open the syllabus for network security", "do you have the slides for module 5",
        "pull up teaching notes module 6", "show me my cover letter", "i need the lab 7 instructions", "can you find my resume",
        "do you have teaching notes for module 5 and 6 for network security", "open my study guide for week 3", "where did i put my transcript",
        "find morgan-white pdf in documents", "where is the planner", "get me the quiz for module 4", "bring up the syllabus",
        "can you pull up the cloud slides for week 2", "grab the teaching notes for module 7", "locate my resume", "open up my resume",
    ],
    "reminders": [
        "what reminders do i have", "cancel reminder about mom", "show reminders", "do i have any reminders", "my reminders",
        "list my reminders", "delete the reminder to stretch", "any reminders set", "what texts are scheduled", "what am i being reminded about",
    ],
    # ---- stuck on a task: the five-minute first step, on a free model
    "stuck": [
        "im stuck", "i'm stuck", "i'm stuck on lab 7", "stuck on read chapter 5", "help me start read chapter 5", "i dont know where to start",
        "help me with network traffic analyzer", "break this down", "how do i start lab 7", "i cant get started", "i can't get started on the week 4 discussion",
        "help me get started", "this is overwhelming", "where do i even begin with lab 7", "break down the network traffic analyzer for me",
        "what's the first step for lab 7", "give me a first step", "i'm overwhelmed", "help me begin the paypal hackathon project",
    ],
    # ---- things done with buttons: a one-line answer that says where, never a model
    "action": [
        "done", "i finished read chapter 5", "mark lab 7 done", "i'm done with the reading", "finished the week 4 discussion", "snooze this",
        "snooze for an hour", "skip this", "not this one", "pin lab 7", "start", "start the timer", "take a break", "i need a break",
        "low energy", "turn on low energy mode", "i'm tired", "complete read chapter 5", "check off lab 7", "start working", "begin", "lets go",
        "pause", "stop the timer", "i did it", "all done", "mark it done", "i completed lab 7", "can't right now",
    ],
    # ---- too little to act on: ask for the whole thought, never a model
    "tiny": ["number 1", "1", "yes", "the first one", "ok", "no", "that one", "sure", "thanks", "k", "hi", "hello", "hey", "?", "lol", "nvm", "never mind",
             "help", "i need help", "what can you do", "what can i ask", "how does this work"],
    # ---- ordinary questions and small asks: a free model, no classifier call
    "free": [
        "what is a subnet mask", "explain the tcp handshake", "how do i center a div", "what's the difference between tcp and udp",
        "give me 5 name ideas for a golf app", "how do you spell necessary", "what's 15% of 80", "what does idempotent mean",
        "what is a security group in aws", "how does oauth work", "explain what a firewall does", "what's a good way to study for a midterm",
        "define zero trust", "whats the difference between authentication and authorization", "how do i delete a git branch",
        "what is iam in aws", "can you explain public key encryption", "tell me a joke", "how long should a cover letter be",
        "what's the command to list files in linux", "how do i undo a git commit", "what port does ssh use", "why is the sky blue",
        "summarize the osi model", "write a short email to my professor asking for an extension", "reword this: i am writing to ask about the role",
        "what's a pgd attack", "what does fgsm stand for", "how do i exit vim", "is python or go better for a packet sniffer",
        "give me a study tip", "quiz me on subnetting", "what are the osi layers", "how do i make a venv in python",
        "whats a good breakfast before golf", "translate good morning to spanish", "how many ounces in a cup", "what's a cron job",
        "can you tell me what a vpc is", "i dont understand what a nat gateway does", "help me understand dns", "explain it like im five: tls",
        "what time zone is atlanta in", "how do i password protect a zip file", "what is prompt injection",
        "break down the osi model", "what should i do about my landlord", "what should i name my golf app", "suggest a name for my packet sniffer",
        "what is the next step in the tcp handshake", "how do i start a venv",
    ],
    # ---- real work for a model: these are meant to reach the classifier
    "jev": [
        "refactor the import pipeline to use async and update the tests", "write a cover letter for the federal reserve internship",
        "debug why my launchd job keeps failing after sleep", "build a script that renames all my lecture files by week",
        "write a function in dates.py that counts weekdays between two dates", "review my resume and rewrite the summary section",
        "design a schema for my golf stats app", "help me write a cover letter", "should i take the fed internship or the chase one",
        "can you delete all the files in my repo and then rebuild", "why does my launchd job keep failing after sleep",
        "fix the bug in import.py", "help me with my resume",
    ],
}

# second batch: written after the rules, as a check on phrasings the rules had not seen
MORE = {'now': ['alright what am i doing', 'whats the first thing i should do', 'so what do i start with today', "what's the one thing i should do right now", 'ok whats next on the list', 'what should i get started on', 'i have an hour, what should i do', "i'm free now what should i work on", 'what would you do first', 'where should i put my energy today', 'whats most urgent', "what's the most urgent thing"],
    'schedule': ['whats due this wk', 'do i have anything due', "what's coming due", "anything i'm forgetting this week", 'how far behind am i', "what's due in the next 3 days", 'what assignments do i have this week', 'is there homework due tomorrow', "what's my deadline for lab 7", "when's lab 7 due", 'do i have a test thursday', 'whats on the calendar today', 'what do i have going on tomorrow', 'anything late'],
    'capture': ['remind me tmrw to call the bank', 'i need to buy a birthday gift for gianna', 'need to schedule an oil change', "don't let me forget my dentist appointment friday", 'put laundry on my list', 'add a reminder to take out the trash tonight', 'i have to submit the fafsa by friday', 'get groceries tomorrow', 'text gianna back', 'can you add renew my license to personal', 'jot down: ask professor about extra credit', 'i keep forgetting to water the plants', 'work on the analyzer every tuesday and thursday', 'study for the midterm thursday'],
    'stuck': ['i have no idea where to start on lab 7', 'im so stuck on this lab', 'can you help me get started on read chapter 5', 'i dont know how to begin', "i'm frozen", "help i'm stuck", "what's the smallest first step"],
    'action': ['im done', 'ok done', 'finished it', 'i finished the lab', "let's start", 'stop', 'skip it', "i'm exhausted", 'not feeling it today', 'snooze it till tomorrow'],
    'project': ['where was i on the analyzer', "what's going on with the analyzer", 'how far did i get on the analyzer', 'where did i leave the analyzer', 'analyzer status'],
    'lookup': ["where's the syllabus", 'pull up my resume', 'find the slides for module 3', 'do you have the study guide for week 2', 'open the lab 7 pdf'],
    'free': ['whats a vlan', 'how does dns work', "what's the difference between a vpc and a subnet", 'give me a mnemonic for the osi model', 'how do i write a for loop in python', 'can you explain what kerberos is', 'what does cia stand for in security', 'is 8 hours of sleep enough', 'how do you pronounce nginx', 'who invented the internet', "what's a good golf drill for putting", 'give me three interview questions for a soc analyst role', 'what are common ports i should memorize'],
    'tiny': ['yep', 'ok cool', 'idk', 'hm', '2']}
for _k, _v in MORE.items():
    CASES[_k] = CASES[_k] + _v

# third batch, also written after the rules
MORE2 = {'now': ["what's the game plan", 'what am i working on first', 'what do i start today with', 'so where do we begin', 'what is the best thing to do right now', "tell me what's next", 'what should come first today', 'which task is the most important', 'what do i need to focus on', 'what needs my attention right now', 'got 30 minutes what should i do', "what's the next thing on my list"],
    'schedule': ["how's my week looking", 'am i caught up', 'what do i still have to do this week', 'anything due before friday', "what's due by sunday", 'how many labs do i have left', "what's my homework for this week", 'is there anything i need to turn in tomorrow', "what's overdue", 'do i have anything late', "what's due for cloud this week", 'what internships stuff is due', 'how loaded is tomorrow'],
    'capture': ['remind me to take my meds every night', 'i need to call the registrar on monday', 'add dentist appointment thursday at 2pm', "dont forget gianna's birthday dinner saturday", 'gotta finish the cloud lab tonight', 'remind me about the career fair next tuesday', 'i should update my linkedin', 'note: ask about parking pass', 'schedule a haircut', 'buy golf balls', 'i want to practice putting twice a week', 'make sure i pay the internet bill by the 15th', 'need to return my textbook', 'put call grandma on my list for sunday'],
    'stuck': ["i'm stuck on the week 4 discussion", 'no clue how to start read chapter 5', 'im overwhelmed by lab 7', "can't make myself start", "i'm lost on lab 7", 'feeling stuck'],
    'action': ['done!', 'finished read chapter 5', 'all finished', 'pause the timer', 'i need to stop', 'skip', 'snooze this for an hour', 'i feel sick', 'start it', "i'm burnt out"],
    'project': ['where am i with the analyzer', "what's the latest with the network traffic analyzer", 'update me on the analyzer', 'how is the analyzer going', 'where did i leave off on the analyzer project'],
    'lookup': ['find my cover letter', 'where is my resume', 'open teaching notes for module 2', 'pull up the syllabus for cloud', 'show me the slides for week 4'],
    'reminders': ['what reminders are set', 'show my reminders', 'remove the reminder about meds'],
    'park': ['idea: golf score tracker', 'i have an idea for a study timer app', 'park this: learn rust'],
    'free': ["what's a dmz in networking", 'how do i rename a branch in git', "what's the capital of australia", "explain nat like i'm new", 'how many bits in an ipv6 address', 'what does tls protect against', 'give me two ideas for a portfolio project', 'is it ok to list coursework on a resume', 'what are good questions to ask an interviewer', 'how do i convert a pdf to word', 'difference between ids and ips', 'what does sudo do'],
    'tiny': ['yeah', 'okay', 'cool', 'thanks!', '3']}
for _k, _v in MORE2.items():
    CASES[_k] = CASES[_k] + _v

# fourth batch, also written after the rules
MORE3 = {'now': ["what's up first", 'what do i do with my afternoon', 'i just sat down, what should i do', 'what should i knock out first', 'okay what are we doing', "what's the top thing right now", 'which one should i start with', 'what should i be working on right now'],
    'schedule': ["what's due the rest of the week", 'how much is due tomorrow', 'what do i have due on thursday', 'anything overdue for network security', 'what are my deadlines', "what's coming up next week", 'am i behind in cloud', 'do i have anything due this weekend'],
    'capture': ['remind me friday to email my advisor', 'i need to pick up my prescription', 'add call the landlord', "don't forget to order a cake for gianna", 'i have to study for the cloud test tomorrow', 'pay tuition by dec 1', 'remind me every sunday to plan my week', 'book a flight home for thanksgiving', 'add go for a walk to my list', 'i need to schedule my advising appointment'],
    'stuck': ['stuck on the week 4 discussion', "i can't start lab 7", "i don't know where to begin with read chapter 5", 'help me start'],
    'action': ["i'm done", 'done for now', 'i finished lab 7', "let's begin", "i'm drained today", 'next one please'],
    'project': ['where did i leave off on the network traffic analyzer', "how's the network traffic analyzer coming along", 'what was i doing'],
    'lookup': ["where's my cover letter", 'find the syllabus', 'do you have slides for module 2'],
    'free': ['what is nmap', 'how do i ssh into a server', 'why is my wifi slow', "what's a good python library for packets", 'explain subnetting simply', "what's the average salary for a security analyst", 'how do i cite a website in apa', 'what does a soc analyst do'],
    'tiny': ['sure thing', 'no thanks', 'ok thanks'],
    'jev': ['write a python script that parses pcap files and prints the top talkers', 'rewrite my resume summary for a cloud security role', 'figure out why the dashboard server crashes on startup']}
for _k, _v in MORE3.items():
    CASES[_k] = CASES[_k] + _v

MORE4 = {'capture': ['work on the bandit wargame twice weekly', 'work on bandit 2x a week', 'work on bandit 2 days a week', 'work on bandit a couple times a week', 'add a playground task to work on bandit twice a wk']}
for _k, _v in MORE4.items():
    CASES[_k] = CASES[_k] + _v

# casual batches (typos, no apostrophes, lowercase, short forms), written blind before the rules were changed
MORE5 = {
    'now': ['wut should i do rn', 'wat do i do now', 'whats up next for me', 'what shud i work on', 'idk what to do rn', 'what do i do first pls', 'tell me what 2 do', 'what should i do lol', 'whatchu want me to do', 'k so what do i do', 'ok so whats next', 'what u got for me', 'whats the plan rn', 'what am i doin', 'wat should i do next', 'hmm what should i work on', "what's on the agenda", 'anything i should be doing', 'what should i do w my time', 'gimme something to work on', 'lemme know what to do', 'i got time what do i do', 'free rn whats next', 'what do i do w myself', 'whats my move', 'bored what should i do', 'what should i do first today', 'where do i begin', 'so what first', 'pick something for me'],
    'schedule': ['whats due', "what's due rn", 'anything due soon', 'whats due this week', 'wats due tmrw', 'do i have stuff due', 'what do i have due tmrw', 'am i late on anything', 'anything overdue', "what's late", 'how much homework do i have', 'how many labs left', 'whats left to do', "what's on for tomorrow", 'what do i got due friday', 'any deadlines coming up', 'whats the next deadline', 'when is the next thing due', 'anything due this wknd', 'do i have anything due monday', 'what do i owe', 'am i caught up on everything', 'how behind am i', 'is anything due today', "what's due tonight", 'got anything due tmrw', "tell me what's due", "what's due next week", "list what's due", "how's my week"],
    'capture': ['remind me tmrw to email prof', 'i gotta call the dentist', 'need to buy milk', 'add laundry', 'add call mom to my list', 'reminder: pay rent fri', 'remind me to take out trash tonight', 'dont let me forget to submit lab 8', 'i need to renew my passport', 'put dentist thursday 2pm', 'gotta get gas', 'lemme add buy a charger', 'pls remind me to stretch at 5pm', 'text me at 8pm to call grandma', 'i have to finish the essay by sunday', 'add finish lab 9 for network security', 'remind me to apply to deloitte friday', 'can u remind me to call the bank tmrw', 'add a reminder for my meds at 9pm', 'schedule oil change next week', 'i should email my advisor', 'need to pick up groceries tonight', 'remind me to drink water every day', "don't forget the career fair tuesday", 'todo: wash car', 'new task finish slides', 'can u add buy stamps', 'i forgot to pay my phone bill add it', 'add vacuum the apartment saturday', 'set a reminder for tmrw 10am to call the dentist'],
    'action': ['done', 'did it', 'finished', "i'm done w it", 'ok finished that', 'just finished lab 7', 'completed read chapter 5', 'knocked out the reading', 'check off read chapter 5', 'i did the reading', 'snooze', 'not now', 'later', 'skip it', 'give me something else', 'pin lab 7', 'pin this', 'unpin', 'start', 'lets go', 'starting now', "i'm starting", 'take a break', 'need a break', 'low energy', 'im tired', 'im wiped', 'not feeling it'],
    'stuck': ['im stuck lol', 'stuck on lab 7', 'idk how to start', 'i have no clue where to start', 'help im stuck on read chapter 5', 'cant start', 'i cant figure out where to begin', 'where do i even start w lab 7', 'break it down for me', 'overwhelmed'],
    'project': ['where was i on the analyzer', 'whats the status of the analyzer', "how's the analyzer going", 'where did i leave off', 'where am i at on the network analyzer', 'what was i doing on the analyzer', 'catch me up on the analyzer', 'analyzer progress', 'status on the analyzer pls', 'last thing i did on the analyzer'],
    'lookup': ['wheres my resume', 'find resume', "where's the syllabus", 'need the module 5 slides', 'get me teaching notes for module 3', 'where are the cloud slides for week 4', 'pull up my resume pls', 'open resume', 'show me the network security syllabus', 'where did i save my cover letter'],
    'park': ['idea: macro pad', 'idea- ctf scoreboard', 'park idea: scraper for job posts', 'i got an idea for a game', 'just thought of an app idea', 'side project idea: pcap visualizer', 'parking lot: smart golf bag tag', 'idea for later: voice notes to tasks', 'note this idea: browser extension', 'put it in the parking lot: auto-resume tailor'],
    'reminders': ['what reminders do i have', 'any texts scheduled', 'show my reminders', 'what am i getting reminded about', 'list reminders', 'cancel the stretch reminder', 'delete my meds reminder', 'what texts are set up', 'do i have reminders', 'remove reminder about dentist'],
    'tiny': ['yup', 'kk', 'ok', 'thx', 'thanks', 'hey', 'yo', 'nah', 'nope', 'lmao'],
    'free': ['whats a vpn', 'how do firewalls work', 'what is xss', 'wats the diff between http and https', 'how do i make a list in python', "what's ssh", 'explain docker to me', 'what is a hash', 'what does dns do', 'how do i git rebase', 'gimme a quick tip for golf', "what's a good protein snack", 'how do i write a for loop in js', 'what is the cia triad', 'what does cors mean', 'whats an api', 'how long is a marathon', 'what is 12 times 15', 'how do i change my git username', "what's a good name for a cat"],
}
for _k, _v in MORE5.items():
    CASES[_k] = CASES[_k] + _v
MORE6 = {
    'now': ['wat do i do first', 'ok soo what do i do', 'whats the move rn', 'what shud i do first', 'hey what should i be doing', 'idk what to work on tell me', 'what task should i do', 'give me my next task', 'i need something to do', 'what is my next task', 'okay what now', "what's my first task today", 'what do i do after this', 'after that what', "so what's the priority", 'what do i attack first', 'what should i get done first', 'what is the most important thing i should do', 'tell me whats next', 'whats next on my list', 'what do i have to do rn', 'um what should i do', 'gimme the next thing', 'just tell me what to do', 'what should i do with the next hour', 'dont know what to do', 'what should i start', 'what am i working on next', 'which assignment should i do first', 'where do i start today'],
    'schedule': ['wats due tonite', "what's due soon", 'anything due in the next few days', 'do i have anything due this week', 'whats due on friday', "what's due the 15th", 'is there anything late', 'am i missing anything', 'did i miss anything due', "what's overdue rn", 'how many assignments are due this week', 'how many things do i have left', 'what do i have left to do for cloud', 'what labs are due', "what's due in network security", 'whats due for internships', 'do i have class tmrw', 'is there a quiz this week', "when's my next test", "what's the next thing due", "what's due next", 'what do i need to turn in', 'anything due before the weekend', "what's the deadline for the discussion", 'when is the week 4 discussion due', 'how packed is my week', 'how busy is tomorrow', 'what does today look like', "what's on for friday", 'am i on track'],
    'capture': ['remind me to call mom tonight', 'need to pick up my meds', 'i need to email my professor', 'can you add call dentist to my list', 'add return shoes to personal', 'i should go to the gym', 'add: buy printer ink', 'gotta do my taxes', 'remember to water the plants', 'remind me friday morning to submit the form', 'remind me to text gianna at 6pm', 'add pay credit card bill due the 20th', 'i have to renew my license by dec 5', 'text me tomorrow at 8am to take my vitamins', 'reminder to bring my id', 'put dentist appointment on my list', 'dont forget to bring snacks', 'i must finish the report', 'i need to apply to the spring internship', 'add study cloud notes to cloud computing', 'can u remind me to move my car', 'please add finish the quiz to network security due friday', 'i gotta pick up the package', 'note to self call the landlord', 'need to buy a gift for mom', 'book the hotel for the trip', 'apply to the nsa internship by dec 1', 'create a task to organize my files', 'make a todo for cleaning my room', 'i need to start my paypal hackathon project'],
    'action': ['im done with the lab', 'finished lab 7', 'i did lab 7', 'all done for now', 'done done', 'skip this', 'snooze for 2 hours', 'snooze lab 7', 'not this one pls', 'pin this one', 'pin read chapter 5', 'starting lab 7', 'start read chapter 5', "i'm gonna start now", 'let me start', 'taking a break', 'need a breather', "i'm beat", 'im exhausted', "i'm wiped out", 'i feel awful today', 'knocked out lab 7', 'wrapped up the reading', 'finished the discussion', 'completed it', 'i got it done', 'mark this done', 'complete this', "i'm ready to start", 'go'],
    'stuck': ['im totally lost', "i don't know what to do with lab 7", 'stuck on the analyzer', 'where do i start with the analyzer', 'i cant figure out where to start', 'help me get going', 'help me get started on lab 7', 'ugh i cant start', 'how do i even begin lab 7', 'not sure how to start read chapter 5'],
    'project': ['where am i at on the analyzer', 'analyzer status', 'how is the network analyzer going', "what's the status of the analyzer project", 'where did i leave the analyzer off', 'catch me up on the network traffic analyzer', 'what was my last commit on the analyzer', 'when did i last work on the analyzer', 'where was i on the network analyzer', 'status update on the analyzer'],
    'lookup': ['do you have the module 3 slides', "where's the week 2 syllabus", 'find my network security syllabus', 'pull up the cloud study guide', 'can you find the teaching notes for module 4', 'i need the quiz for module 2', 'find me the cloud slides', 'show me module 1 slides for network security', 'where are my teaching notes for week 5', 'find the cover letter i wrote for deloitte'],
    'park': ['idea: ai that grades my golf swing', 'idea for a project: rss reader', 'i had an idea for a discord bot', 'park this idea: automatic meal prep', 'random thought: build a typing test', 'new idea: study buddy bot', 'idea: portfolio site redesign', 'i got an idea: wifi password qr maker', 'idea- tiny status bar app'],
    'reminders': ['what reminders do i have set', 'any reminders', 'cancel my reminders', 'cancel the call mom reminder', 'list my reminders', 'what am i reminded of', 'delete reminder about stretch', 'remove the dentist reminder', 'what texts do i have scheduled', 'do i have any texts coming'],
    'tiny': ['thanks!', 'ok thanks', 'hi', 'hey there', 'good morning', 'yes', 'no thanks', 'hello', 'sup', 'cool'],
    'free': ['whats a subnet', 'how do i reverse a string in python', "what's the difference between a list and a tuple", 'what does git stash do', 'how do i make coffee', 'what is a reverse proxy', 'explain mfa', 'who wrote the cia triad', 'how do i get better at golf putting', "what's the best way to learn linux", "what's an ssl cert", 'can u explain what a hash collision is', 'how do i flush dns on mac', "what's the difference between symmetric and asymmetric encryption"],
}
for _k, _v in MORE6.items():
    CASES[_k] = CASES[_k] + _v

MORE7 = {
    'now': ['WHAT SHOULD I DO', 'what do i do rn pls', 'ok what should i be doing right now lol', 'um so whats the plan', 'so like what do i do', "what's my next move", 'hmm whatever, what do i do', "just tell me what's next", 'ok and now?', 'k whats next', 'what to do', 'what should i do now?!', 'what do i do today', 'what should i do next pls', 'tell me whats up next', "I'm free. What should I do?", 'I finished that. What now?', "what's the best use of my time right now", 'what are we doing now', 'where should i focus', "what's the thing i should be doing", 'whatever, pick for me', 'what else do i have to do', 'help me decide what to do', 'not sure what to do next', 'i dunno what to work on', 'time to work, what do i do', 'time for work what first', 'what do i work on rn'],
    'schedule': ['anything due??', "what's due!!", 'whats due on monday', "what's due the rest of today", 'what do i have this week', 'what do i have tmrw', 'anything due on the 20th', 'anything for network security this week', 'is lab 7 due soon', "what's my next assignment due", 'how many deadlines this week', 'any homework tonight', 'do i have class on thursday', 'is there class tonight', 'what time is class tomorrow', 'when does class start tonight', 'is there a test tomorrow', 'do i have a test this week', "what's due before friday", 'anything due by monday', "what's the next quiz", 'which assignments are late', "what haven't i turned in", "what's due this weekend", 'am i behind in network security', "how's the week looking", 'how much is due by friday', 'how many labs are left in cloud', 'what is due on the 18th', "what's on my list for today", "what's left to do right now"],
    'capture': ['Remind me to call the vet tomorrow at 4', 'remind me to take my pills at 8pm daily', 'i have to get my car inspected', 'gotta buy a new keyboard', 'ok add return the textbook to my list', 'remind me next monday to email the registrar', 'need to mail the check by friday', 'text me tmrw morning to pack', 'i want to practice golf on saturday', 'book a table for friday night', 'buy flowers for gianna', 'need a haircut', 'pls add mow the lawn', 'add: laundry tonight', 'reminder - renew car insurance', 'i need to renew my tags this month', 'can you put dentist on my list', 'add finish capstone proposal to school', 'write down: ask about the stipend', 'jot down call insurance', 'note: email recruiter', 'add a new task called clean my desk', 'new task: finish handshake profile', "i've got to call my mom", 'i have to do laundry', "i'd like to practice putting every day", 'i gotta run to the store', 'ill need to bring my laptop tomorrow', 'setup a reminder for the 5th to pay rent', 'please remind me to eat lunch at noon'],
    'action': ['DONE', 'finished!', 'finished lab 7!', 'im done lol', "i'm done with that", 'did the reading', 'ok i finished', 'knocked that out', "i'm starting now", 'starting read chapter 5 now', 'begin lab 7', 'lets begin', "i'm starting lab 7", 'snooze it for a while', 'not this one, something else', 'skip that one', 'pin lab 7 pls', 'can you pin this', 'need a break', 'time for a break', "i'm taking a break now", 'break please', "i'm so tired", 'im really tired today', 'low energy day', 'not feeling well today', "i'm sick today", 'turn low energy mode on', 'wiped', 'stop timer'],
    'stuck': ["i'm stuck on lab 7 lol", 'stuck pls help', 'cant start lab 7', 'where do i start with the discussion', 'how do i start the week 4 discussion', 'help me get started on the analyzer', 'i dont know how to start lab 7', 'im frozen on this', 'feeling overwhelmed', 'so overwhelmed rn'],
    'project': ['analyzer: where was i', 'where were we on the analyzer', 'where am i with the network analyzer', "what's the progress on the analyzer", 'what did i do on the analyzer', 'how far along is the analyzer', 'what is the status of the analyzer', 'where did i end up on the analyzer', 'status check on the analyzer', 'analyzer update'],
    'lookup': ['wheres the cloud syllabus', 'pull up the network security syllabus', 'where did i save my resume', 'open teaching notes module 1', 'get the module 6 slides', 'open the week 3 slides for cloud', 'find resume pdf', 'find my cover letter for the fed', 'where are the quizzes for module 5', 'show teaching notes for week 2'],
    'park': ['idea: raspberry pi weather station', 'idea: build a recipe scraper', 'i just thought of a cool game idea', 'park idea: bluetooth finder', 'parking lot: terminal dashboard', 'new idea: golf club tracker', 'idea: automate my invoices', 'side project idea: log parser', 'put this in the parking lot: dns visualizer', 'idea - cli for flashcards'],
    'reminders': ['what reminders are scheduled', 'cancel the dentist reminder', 'delete the stretch reminder', 'clear my reminders', 'show my texts', 'what am i getting texts about', 'any upcoming reminders', 'are there any reminders', 'what reminders are set up'],
    'tiny': ['thx', 'ok', 'k', 'yes', 'no', 'yea', 'nvm', 'hi!', 'hey!', 'okay'],
    'free': ['whats dns', 'how do i undo in vim', "what's the difference between a process and a thread", 'how do i cook rice', "what's a good warmup for golf", 'explain cors', 'what does rsa stand for', 'how do i reset my wifi router', 'how many weeks in a year', 'what is a botnet', 'how do i say thank you in french', 'give me a fun fact', 'what is kerberoasting', 'what is the cia triad in security', 'how do i find my ip address'],
}
for _k, _v in MORE7.items():
    CASES[_k] = CASES[_k] + _v
