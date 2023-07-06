#!/usr/bin/python3

from email.policy import default
import argparse
import urllib.request
import sys
import logging


# MAIN
def main():
    # parse command line arguments
    parser=argparse.ArgumentParser()
    parser.add_argument("-v", "--version", type=str, default="0.18.0", help="the version number of jmx_prometheus_javaagent")
    parser.add_argument("-o", "--output", type=str, default="/minecraft/jmx_prometheus_javaagent.jar", help="output path of the jar")
    args=parser.parse_args()

    FORMAT = '%(asctime)-15s [%(name)s][%(levelname)s]: %(message)s'
    logging.basicConfig(format=FORMAT, level="INFO")

    try:
        version = args.version
        url = f"https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/{version}/jmx_prometheus_javaagent-{version}.jar"
        urllib.request.urlretrieve(url, args.output)
    except IOError as e:
        print("I/O Error. Download aborted. {}".format(e), file=sys.stderr)
        sys.exit(2)
    except:
        logging.exception("Unexpected error", stack_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()