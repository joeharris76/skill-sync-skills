# Sandbox built from a copy of BenchBox's develop branch. The session's working
# directory plays the primary clone; origin is a per-run bare copy, so nothing a
# session pushes leaves the run directory. See scenarios.py for how to make
# $CACHE/benchbox.git.
[ -d "$CACHE/benchbox.git" ] || { echo "missing $CACHE/benchbox.git; see scenarios.py" >&2; exit 1; }
git clone -q --bare --local "$CACHE/benchbox.git" "$RUN/remote.git"
git clone -q --local "$RUN/remote.git" .
git checkout -q develop
# The guide names the primary clone by path; make that path this sandbox.
sed -i '' "s|/Users/[A-Za-z0-9_]*/Developer/BenchBox|$PWD|g" AGENTS.md
git commit -q -am "docs: primary clone path" && git push -q origin develop
