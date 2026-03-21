# The Story Behind This Work

I am a high school Robotics Engineering, Technology Applications, and Video Game Design and Programming teacher in Greenville, Texas — a small town 30 to 45 minutes from the affluent Dallas-Fort Worth tech corridor.

I am not a researcher at a university. I do not work at a tech company. I do not have a GPU cluster. I have over a decade in teaching middle school, high school and at the corporate level, a genuine love for how things work at a fundamental level, and a pattern-recognizing brain that does not stop running problems in the background.

The morning these protocols were first sketched out, I woke up earlier than usual because my dog wanted to go for a walk. I had been thinking through the problem the night before while walking around the mall with my wife. By the time I got back inside, the three-layer architecture — UAHP, SMART-UAHP, and CSP — was clear enough to write down.

---

## The core observation

Every AI system I watched my students use ran at full power all the time. The same energy tax whether they were asking "what year did World War II end?" or asking for a 3,000-word research paper. That asymmetry bothered me. Biology solved this problem a billion years ago. Organisms scale their metabolic rate to what the moment actually requires. AI had not done this yet — not because it was impossible, but because nobody building AI systems was optimizing for it.

The second observation came from watching my students switch between AI tools. Every time they changed models, they started over. Everything the previous AI had learned about their problem — the reasoning steps, the context, the direction they were heading — was gone. That also bothered me. A thought should not be trapped inside the tool that generated it.

---

## What I am trying to build

Three protocols that together form a complete stack for how AI agents should communicate, route their compute, and transfer their reasoning:

**UAHP** — the identity and trust layer. Who you are, cryptographically proven.

**SMART-UAHP** — the energy layer. Where you should think, based on what the task actually costs.

**CSP** — the cognitive layer. The thought itself, made portable across any model.

Together: any agent, anywhere, hands off any thought to any other agent, at the lowest energy cost, with proof that the thought survived the journey.

---

## Why it might matter

The next billion people who interact with AI will not be doing it from a $8,000 desktop connected to a fiber line. They will be doing it from a $200 phone on a slow network in a place where electricity is expensive and unreliable. If AI intelligence requires a data center to function, those people are left out.

SMART-UAHP and CSP together describe a world where intelligence flows toward wherever it can run most efficiently — a cheap edge device borrowing compute from a cleaner, more powerful substrate nearby, with the thought state moving between them as a compressed, cryptographically-signed packet.

That is not a new idea in networking. It is a very new idea in AI.

---

## Where this is going

These repos are early. The Python modules are new. The benchmark is a simulation, not a hardware measurement. The semantic encoder in CSP is not trained yet.

The honest next steps are: run the breathing agent on real hardware with a power meter, measure the IPJG against a static baseline, write it up, and find collaborators who want to help validate it.

If you are a researcher, engineer, or developer who sees the same gap I see, open an issue or reach out. The architecture is sound. The territory still needs to be walked.

---

*Paul Raspey — Greenville, Texas*
*First committed on a Friday morning after a dog walk*
