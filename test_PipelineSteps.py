import shutil
import tarfile
import gzip
import pytest
import requests


@pytest.fixture(scope="session")
def get_fastq_test_data(tmp_path_factory):
    # download test fastq data, extract and remove after test completion
    domain = ".".join([
        "ont-exd-int-s3-euwst1-epi2me-labs",
        "s3-eu-west-1", "amazonaws", "com"
    ])
    url = "https://" + domain + "/fast_introduction/"
    req = requests.get(url + "archive.tar.gz")
    assert req.status_code == 200

    fastq_data = tmp_path_factory.mktemp("tmp_data") / "fastq"
    fastq_data.mkdir()
    with open(fastq_data / "archive.tar.gz", 'wb') as fh:
        fh.write(req.content)
    with tarfile.open(fastq_data / "archive.tar.gz", 'r:gz') as tarfh:
        with open(fastq_data / "example1.fastq", 'wb') as fh:
            fh.write(tarfh.extractfile("test0/fail/example1.fastq").read())
        with open(fastq_data / "example2.fastq", 'wb') as fh:
            fh.write(tarfh.extractfile("test0/pass/example2.fastq").read())
        with gzip.open(fastq_data / "example3.fastq.gz", 'wb') as fh:
            fh.write(tarfh.extractfile("test0/example3.fastq").read())
        print(fastq_data)
    yield fastq_data
    shutil.rmtree(fastq_data)

