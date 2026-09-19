# Lab 01 — Context, Skills and Commands

## Goal

Get comfortable managing context and writing/using skills.

Manage context manually by clearing and/or compacting.
Use `/context` to see how context is being used.


## grill-me Skill

The following skill is from Matt Pocock (https://github.com/mattpocock/skills/blob/main/grill-me/SKILL.md).

It helps walk you through the thought process behind a design.

It is proof that a skill does not have to be long.

Add this as a local skill (.claude/skills/grill-me/SKILL.md)
by copying `grill-me.md` to `.claude/skills/grill-me/SKILL.md`.


## Get grilled about some possible code project

Start claude code.

Give it a prompt something like this (use a non-trivial, but small objective):

```
I need to write C++ code that [INSERT SOME OBJECTIVE]. Grill me.
```

Did the model proceed with a grilling session? If not, explicit type `/grill-me`.

After the last question, the context should now be full of your discussion, including all the grilling questions and answers.

Type `/context` to see the breakdown.


## Exit claude code

## PRD Skill

Add Matt's to-prd skill to your local directory of claude code skills
by copying `to-prd.md` to `.claude/skills/to-prd/SKILL.md`.

## Run claude code

Use the `/resume` command to resume the conversation where you did the grill-me session.
This will have you resume exactly where you left off.
Run `/context` to see that the context is the same as it was before.

Invoke the `to-prd` skill. Answer any questions, and after it is done, a file should appear in the `prds` directory with a PRD that describes the project you had described earlier.


## Create your own skills

Install the Anthropic Skill Creator skill.

Type the `/plugins` command, and scroll down to the `skill-creator`, hit enter and follow the instructions to install this skill. It will help you create skills without doing the manual file editing.

Write a skill that, given a path to a PRD, will create a BDD style set of test specifications.

Write a skill that, given a path to a PRD and a set of test specifications, will implement the PRD and tests in C++.

BONUS: Write a skill that includes a script that gets executed (doesn't matter what it does, this is just experimenting).

Writing skills is more an art form.
Look at skills others have written.
Experiment with different models to see how they perform with your manual commands.
As any development, iteration and testing are the best ways to develop skills.
Remember, a skill can include other resources, including scripts or any other files.


Also, Claude Code should be able to help you develop skills. Ask it for help when you need it.
