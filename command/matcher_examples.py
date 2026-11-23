"""Extra example sentences for the meaning matcher (command/matcher.py), added on top of the phrase tables.

Kept in their own file so the phrase tables can change without touching these. None of these may appear in the held-out
set (command/tests/matcher_heldout.py on branch test/matcher-eval): if one does, that sentence stops being a test.

EXTRA maps label -> sentences. Labels are the matcher's own (see matcher.LABELS).
"""

EXTRA = {
    # Open factual questions. They have nothing to do with her tasks, so the box should chat, not look anything up.
    "general": [
        "how do volcanoes erupt", "why is the sky blue", "what's the capital of peru", "how does dns work", "explain recursion to me",
        "what causes earthquakes", "how do airplanes stay up", "who wrote pride and prejudice", "what is the speed of light",
        "how does a vaccine work", "why do cats purr", "what is inflation", "how do magnets work", "explain what a black hole is",
        "what's the difference between a virus and a bacteria", "how many bones are in the human body", "why is the ocean salty",
        "what does a gpu do", "how does wifi work", "who invented the telephone", "what is photosynthesis", "how do tides work",
        "why do we dream", "what is the tallest mountain on earth", "explain how a blockchain works", "what is a prime number",
        "how does the stock market work", "why is the moon different sizes", "what's the boiling point of water at altitude",
        "how do bees make honey", "what is machine learning", "explain the water cycle", "how does gps know where i am",
        "what year did the berlin wall fall", "why do onions make you cry", "what is the pythagorean theorem",
        "how does encryption keep data safe", "what's the population of japan", "tell me a fun fact about octopuses",
        "how does a refrigerator work",
    ],
    # Statements about other people or plain facts. Never a command to the box.
    "noact": [
        "mom needs to pick out a present", "sam has to finish his lab", "the store closes at 9", "my roommate forgot to pay rent",
        "dad needs to renew his license", "the library opens at 8", "my sister has to call the bank", "jake needs to submit his form",
        "the lab was due yesterday for everyone", "my professor has to grade the quizzes", "the dentist is closed on fridays",
        "she needs to return her library books", "my brother has a test tomorrow", "the deadline for fafsa passed last month",
        "our team has to ship the release", "my cousin has to move out this week", "grandma needs to take her pills",
        "the bus leaves at 5", "my friend should email his advisor", "the semester ends in december",
        "he needs to pick up his package", "my aunt has to book a flight", "the grocery store is out of eggs",
        "mom has to sign the lease", "my partner needs to buy groceries",
    ],
    # The command twin of each statement above: she wants it on her own list.
    "capture": [
        "remind me to buy a gift for my mom", "put finish my lab on my list", "i need to close the store account before 9",
        "remind me to pay rent", "add renew my license to my list", "remind me to open the library card thing", "remind me to call the bank",
        "i have to submit my form", "add grade the quizzes to my list", "remind me to book the dentist", "i have to return my library books",
        "add study for my test to my list", "remind me to file the fafsa", "i need to ship the release", "remind me to move my stuff out",
        "put take my pills on the list", "remind me to catch the 5 bus", "i should email my advisor",
        "remind me to pick up my package", "i have to book a flight", "remind me to buy eggs", "i need to sign my lease",
        "remind me to buy groceries", "add call the landlord to my list", "i gotta mail the check",
    ],
    "stuck": [
        "i don't know where to start", "this lab is too big and i can't begin", "i keep staring at the screen", "i can't make myself open this assignment",
        "so overwhelmed right now", "my brain won't get going on this", "i'm lost on this assignment", "no clue how to approach this",
        "can't focus, need a tiny first step", "everything feels like too much", "i'm blanking on this task", "frozen, help me get going",
        "give me something small to start with", "how do i even begin this project", "stuck again lol", "i've been avoiding this for days",
        "help me break this down", "too much to do, can't pick a first move", "i need a first step", "paralyzed on this one",
    ],
    "park": [
        "park this idea for later", "save this thought for my playground", "idea: a script that sorts my screenshots by date",
        "put this in the parking lot: build a flashcard app", "stash this idea: track my golf scores", "note for later: try a ctf this weekend",
        "random idea, a game about sleep", "jot this down for the playground: learn blender", "i had an idea, an app for gym splits",
        "park it: redo my portfolio colors", "idea for later: automate my receipts", "save for later: look into rust",
        "toss this in the parking lot, a tool that sorts my downloads", "keep this idea: a discord bot for study groups",
        "store this thought: a map of my favorite courses", "remember this idea: sync my notes to my phone",
        "idea dump: a tracker for my gaming hours", "park: try making a synth in python", "bookmark this idea: a better lab template",
        "put it on the someday pile: write a blog about my projects",
    ],
    "lookup": [
        "where's my resume", "can you find the lab 7 instructions", "pull up my teaching notes for week 3", "where did i save the syllabus",
        "do i have notes on subnetting", "find the cloud midterm study guide", "open my cover letter for acme", "where is that pdf from class",
        "got the slides for module 4 somewhere", "show me the file for the network analyzer readme", "dig up my old resume",
        "which folder has the aws lab guide", "locate my transcript", "any notes on iam policies", "find me the week 5 slides",
        "where are my security notes", "look for the project proposal doc", "do you have the quiz review sheet",
        "find that spreadsheet with my applications", "open the cloud lab guide",
    ],
}
