# 12: Look up concepts with Tavily and cite the source

**What to build:** When the learner asks about a concept, the backend makes a real runtime call to the Tavily API, and the explanation names the source in an on-screen label.

**Blocked by:** 04, 01

**Status:** ready-for-agent

- [x] A concept question triggers a Tavily search at runtime (the model replies with a search request; the backend calls Tavily; the model answers with the results)
- [x] The source name appears in the caption (the model names it; the app adds a 'Source: site' line under the last step). Not a label on the canvas
- [x] If Tavily is unavailable the turn still completes without the citation
- [x] Tests use a recorded lookup response (test_tavily.py)
- [x] The Tavily call is visible in the turn trace (trace.lookups, response.sources, and the Lookups metric)

Verified live: 'Who first proved the Pythagorean theorem? Give me the source' made one search and cited Vietnamese Wikipedia; a question about what is on screen made none. At most one search per turn.
