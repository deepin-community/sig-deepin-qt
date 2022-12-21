import sh
import sys
import argparse
from typing import Dict
from pathlib import Path
from datetime import date, timedelta, datetime


def check_pick(repo_name: str, from_date: str, to_date: str) -> list[str]:
    repo_path = "{0}.git/".format(repo_name)
    result: list[str] = []
    fetch_update = True
    if not Path("{0}.git/".format(repo_name)).exists():
        remote_url = "https://github.com/qt/{0}".format(repo_name)
        print("Shadow cloning {0} from {1}".format(repo_name, remote_url))
        sh.git.clone(remote_url, bare=True, depth=1, _out=sys.stdout, _err=sys.stderr)

    git = sh.git.bake('-C', repo_path, _tty_out=False)
    if fetch_update:
        print("Fetching {0} from origin, shallow-since={1}...".format(repo_name, from_date))
        try:
            git.fetch("origin", shallow_since=from_date, _out=sys.stdout, _err=sys.stderr)
        except sh.ErrorReturnCode_128:
            print("{0}: Got return code 128, repo might not have new commits since {1}".format(repo_name, from_date))
            return result
        else:
            print("Done.")

    range_log = git.log(since=from_date, until=to_date, pretty='format:%H')
    commithashs: list[str] = range_log.stdout.decode("utf-8").split('\n')

    while "" in commithashs:  # if no commit in given date range, it can be an empty string
        commithashs.remove("")

    for commithash in commithashs:
        trailers_exec = git(git.show("-s", commithash, format='%b'), "interpret-trailers", "--parse")
        trailers = trailers_exec.stdout.decode("utf-8").split('\n')
        for trailer in trailers:
            if trailer.startswith("Pick-to:") and "5.15" in trailer:
                result.append(commithash)
    print("{0}: {1}/{2} commit(s) need to be cherry-picked".format(repo_name, len(result), len(commithashs)))
    return result


def query_date(args) -> [str, str]:
    yesterday = date.today() - timedelta(days=1)
    from_date = yesterday if not args.in_date else datetime.strptime(args.in_date, '%Y-%m-%d')
    to_date = from_date + timedelta(days=1)
    return [from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d')]


def main():
    parser = argparse.ArgumentParser(
                    prog='Qt patch backport helper',
                    description='Check commits that might need to backport')
    parser.add_argument('-d', '--dry-run',
                        action='store_true',
                        help='turn on dry-run for debugging')
    parser.add_argument('-i', '--in-date',
                        action='store',
                        help='The date we would like to check',
                        required=False)
    [args, _] = parser.parse_known_args()

    if args.dry_run:
        print("!!! Dry-run !!!")

    [from_date, to_date] = query_date(args)
    repos: list[str] = ["qtbase", "qtwayland", "qtdeclarative"]
    results: Dict[str, list[str]] = {}

    for repo in repos:
        results[repo] = check_pick(repo, from_date, to_date)

    print("-------- RESULT --------")
    print("Commits in {0}:".format(from_date))
    for repo_name, commits in results.items():
        for commit_hash in commits:
            commit_url = "https://github.com/qt/{0}/commit/{1}".format(repo_name, commit_hash)
            issue_title = "{0}: commit {1} may need to apply to 5.15 patch-set".format(repo_name, commit_hash[:7])
            issue_body = "- Date: {0}\n- Commit: {1}".format(from_date, commit_url)
            print(issue_title)
            if not args.dry_run:
                sh.gh.issue.create(title=issue_title, body=issue_body)


if __name__ == "__main__":
    main()
