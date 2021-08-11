import argparse
import hashlib
import os
import logging
from json.decoder import JSONDecodeError
from urllib.parse import urljoin

import requests
import urllib3
from tqdm import tqdm


def main():
    # Disable unverified TLS certificate warnings.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    parser = argparse.ArgumentParser(
        description="A little script for downloading all assets inside a Nexus 3 repository, "
                    "following the repository's format (e.g., Maven 2).")
    parser.add_argument("server",
                        help="Root URL to Nexus 3 server; e.g., https://repo.loadingbyte.com")
    parser.add_argument("repo",
                        help="Name of repository whose assets shall be downloaded; e.g., maven-releases")
    parser.add_argument("-o", metavar="output_dir", dest="output_dir",
                        help="Directory where to store the downladed assets; "
                             "if none is provided, the repository name will be used.")
    parser.add_argument("-n", dest="no_verify", action="store_true",
                        help="Disable the SHA-1 hash verification of downloaded assets.")
    parser.add_argument("-q", dest="quiet", action="store_true",
                        help="Do not print anything but errors and two self-destroying progress bars.")

    args = parser.parse_args()
    server_url = args.server
    repo_name = args.repo
    output_dir = args.output_dir
    no_verify = args.no_verify
    quiet = args.quiet

    if not output_dir:
        output_dir = repo_name
#    if os.path.exists(output_dir):
#        if not quiet:
#            print(f"Output directory '{output_dir}' already exists. Please delete it and then re-run the script.")
#        abort(1)

    if "://" not in server_url:
        server_url = "http://" + server_url

    if not quiet: print("Fetching asset listing...")
    asset_listing = fetch_asset_listing(quiet, server_url, repo_name, output_dir, no_verify) ####
    if not quiet: print("Done!")

    #if not quiet: print("Downloading and verifying assets...")####
    #download_assets(quiet, output_dir, no_verify, asset_listing)####
    #if not quiet: print("Done!")####


def abort(code):
    print("Aborting script!")
    exit(code)


def fetch_asset_listing(quiet, server_url, repo_name, output_dir, no_verify): ####
    asset_api_url = urljoin(server_url, f"service/rest/v1/assets?repository={repo_name}")

    asset_listing = []
    try:
        import json
        file_name = 'metea-data.json'
        f = open(file_name, "r")
        data = json.load(f)
        continuation_token = data['continuation_token']
        print("continuation_token is loaded from file....")
        logging.info("continuation_token is loaded from file....")
        f.close()
    except:
        continuation_token = -1  # -1 is a special value hinting the first iteration

    with tqdm(unit=" API requests", leave=not quiet) as pbar:
        while continuation_token:
            if continuation_token == -1:
                query_url = asset_api_url
            else:
                query_url = f"{asset_api_url}&continuationToken={continuation_token}"

            try:
                resp = requests.get(query_url, auth=('umma', 'uL8TZf99_FN'), verify=False).json()
            except IOError as e:
                pbar.close()
                print(str(e))
                abort(2)
            except JSONDecodeError as e:
                pbar.close()
                print(f"Cannot decode JSON response. Are you sure that the server URL {server_url} is correct and "
                      f"the repository '{repo_name}' actually exists?")
                abort(3)

            continuation_token = resp["continuationToken"]
            ## Save our changes to JSON file
            jsonFile = open(file_name, "w+")
            jsonFile.write(json.dumps({"continuation_token": continuation_token}))
            jsonFile.close()
            asset_listing += resp["items"]
            
            pbar.update()
            
            download_assets(quiet, output_dir, no_verify, resp["items"]) ####
    return asset_listing


def download_assets(quiet, output_dir, no_verify, asset_listing):
    with tqdm(asset_listing, leave=not quiet) as pbar:
        for asset in pbar:
            file_path = os.path.join(output_dir, asset["path"])
            error = download_single_asset(quiet, file_path, no_verify, asset)

            if error:
                pbar.close()
                print(f"Failed downloading '{file_path}' due to the following error:")
                print(error)
                abort(4)


def download_single_asset(quiet, file_path, no_verify, asset):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    for tryy in range(1, 11):
        try:
            r = requests.get(asset["downloadUrl"], auth=('umma', 'uL8TZf99_FN'), verify=False)
            with open(file_path, "wb") as f:
                f.write(r.content)
        except IOError as e:
            # The requests API tries multiple times internally, so if it can't connect, the connection is probably down.
            return str(e)

        if no_verify:
            if not quiet: tqdm.write(f"Downloaded '{file_path}' (not verified!)")
            return False
        elif asset["checksum"]["sha1"] == sha1(file_path):
            if not quiet: tqdm.write(f"Downloaded and verified '{file_path}' (try {tryy})")
            return False
        else:
            tqdm.write(f"SHA-1 Verification failed on '{file_path}' (try {tryy}); retrying...")

    # If, after 10 tries, the SHA-1 hash is still wrong, something's probably corrupted.
    return "Repeated SHA-1 verification failure"


def sha1(file_path):
    with open(file_path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


if __name__ == "__main__":
    main()
