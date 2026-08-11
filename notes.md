11-08-2026

Today I used Codex to create the first version of this tool for accessing text files in a git repo. It was remarkably easy to do,
took about 20 minutes of actual thought over my lunch break today.

All the 'engineering' was done in about 20 conversations with ChatGPT while I couldn't sleep on holiday, so this is very much a
personal project. I already have a private git repo containing a bunch of markdown files organised into ideas, projects, notes and
recollections which I've been collecting over the last few weeks. That's private.

As a test, I pointed this MCP at my instance of that repo here on my development machine.

It was able to answer a question about the intent of something I wrote in there without further prompting.
As a follow on, it was able to review all the ideas and extract some common themes by inference - they are absolutely not
explicitly written in any of the documents.

This is precisely what I wanted to be able to do with the stored memory. Concept proven!

I then sorted out some startup wrinkles for my personal memory in fresh codex sessions. I am looking forward to trying
this out with some other memory repos I have created. For now, it's able to use session memory as working scratch and
top it up with collected curated memory from earlier work without any specific guidance. That feels good.

The big test is going to be taking a new conversation and extracting something for the memory repo. Since Linux does not have
a desktop app, the MCP can't be used there so I'll have to see how that goes.

Check this log out....
"
me: cool. what do I need to do next in the garage project?

codex:
• I’ll look up the garage project’s current notes and outstanding actions in persistent memory.
• Called memory.search_memories({"query":"garage","limit":50})
  └ {"query": "garage", "matches": [], "limit": 50, "truncated": false, "skipped_files": 0}
• Called memory.search_memories({"query":"garage project","limit":50})
  └ {"query": "garage project", "matches": [], "limit": 50, "truncated": false, "skipped_files": 0}
• Called memory.search_memories({"query":"workshop","limit":50})
  └ {"query": "workshop", "matches": [{"path": "INDEX.md", "line_number": 11, "line": "│   ├── garden-workshop.md"}, {"path": "ideas/smart-battery-charging-hub.md", "line_number": 54, "line": "A shed/workshop could use this architecture as a small
        independent DC energy"}, {"path": "projects/garden-workshop.md", "line_number": 1, "line": "# Garden workshop and landscaping"}, {"path": "projects/garden-workshop.md", "line_number": 5, "line": "## Workshop"}, {"path": "projects/garden-
        workshop.md", "line_number": 32, "line": "Run fibre from house to workshop."}, {"path": "projects/garden-workshop.md", "line_number": 36, "line": "pantry -> loft -> soffit/downpipe route -> underground duct -> workshop"}, {"path":
        "projects/garden-workshop.md", "line_number": 40, "line": "Workshop likely receives a UniFi Enterprise 8 PoE switch."}, {"path": "projects/home-network.md", "line_number": 25, "line": "- fibre to workshop"}, {"path": "projects/home-
        network.md", "line_number": 26, "line": "- server relocation to workshop if thermal environment is suitable"}], "limit": 50, "truncated": false, "skipped_files": 0}
• Called memory.read_memory({"path":"projects/garden-workshop.md"})
  └ {"path": "projects/garden-workshop.md", "content": "# Garden workshop and landscaping\n\nStatus: active\n\n## Workshop\n\nApproximate size: 3 x 3.5 m.\n\nPlanned/useful characteristics:\n\n- concrete base\n- insulated construction\n- plywood
        interior\n- EPDM roof\n- ventilated roof cavity\n- roller shutter\n- workbench\n- networking rack\n- space for motorbike\n- eventual 3D printer\n- good lighting\n- fibre networking\n- substantial electrical supply\n\nFloor construction
        currently planned as two layers of 12 mm plywood, glued and\nscrewed.\n\nWalls approximately 18 mm plywood so fixtures can be mounted almost anywhere.\n\n## Network\n\nRun fibre from house to workshop.\n\nLikely route:\n\npantry -> loft ->
        soffit/downpipe route -> underground duct -> workshop\n\nUse preterminated armoured OS2 fibre.\n\nWorkshop likely receives a UniFi Enterprise 8 PoE switch.\n\nAim for a clean labelled installation with accessible joints.\n\n## Immediate
        priority\n\nGet the structure watertight before weather deteriorates.\n\nDo not allow interesting indoor projects to derail this.", "size": 985, "modified_at": "2026-08-11T11:21:33.878735+00:00"}

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

• The next priority is to get the garden workshop structure watertight before the weather deteriorates.

  Focus on completing the external envelope—especially the ventilated roof cavity and EPDM roof—before moving on to attractive indoor work such as the plywood lining, workbench, networking rack, lighting, or fibre installation.

  Your explicit reminder was: don’t let the interesting indoor projects derail weatherproofing.
"

I think that's fascinating. I didn't call it the workshop, codex inferred that from the memories. Notice that there were no matches
for garage in the first two searches. Codex knew to broaden the search for synonyms without me doing anything at all.

I think that definitely proves the concept now.
