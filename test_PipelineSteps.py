import shutil
import tarfile
import gzip
import pytest
import requests

from PipelineSteps import CleanDuplexStep, DuplexStep


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


@pytest.fixture(params=["single", "multiple", "mix"])
def setup_fastq_data(get_fastq_test_data, request):
    data = get_fastq_test_data.parent / "data"
    data.mkdir()
    if request.param == "single":
        shutil.copy(get_fastq_test_data / "example1.fastq", data)
    elif request.param == "multiple":
        shutil.copy(get_fastq_test_data / "example1.fastq", data)
        shutil.copy(get_fastq_test_data / "example2.fastq", data)
    elif request.param == "mix":
        shutil.copy(get_fastq_test_data / "example1.fastq", data)
        shutil.copy(get_fastq_test_data / "example3.fastq.gz", data)
    yield data
    if request.param == "single":
        (data / "example1.fastq").unlink()
        data.rmdir()
    elif request.param == "multiple":
        (data / "example1.fastq").unlink()
        (data / "example2.fastq").unlink()
        data.rmdir()
    elif request.param == "mix":
        (data / "example1.fastq").unlink()
        (data / "example3.fastq.gz").unlink()
        data.rmdir()


@pytest.fixture
def duplex_step(setup_fastq_data, request):
    yield DuplexStep(threads=8)
    clean = request.node.get_closest_marker("clean")
    if not clean:
        shutil.rmtree(setup_fastq_data / f"{setup_fastq_data.stem}_split")
    (setup_fastq_data / f"{setup_fastq_data.stem}.fastq.gz")


@pytest.fixture
def duplex_clean():
    yield CleanDuplexStep()


@pytest.mark.clean(False)
@pytest.mark.needs_conda
# @pytest.mark.skipif("setup_conda == False", reason="No valid conda setup found.")
def test_duplex_step_output(duplex_step, setup_fastq_data):
    duplex_step.run(setup_fastq_data)


@pytest.mark.clean(True)
@pytest.mark.needs_conda
def test_duplex_step_cleanup(duplex_step, duplex_clean, setup_fastq_data):
    duplex_step.run(setup_fastq_data)
    duplex_clean.run()
