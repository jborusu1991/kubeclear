# kubeclear

Tool to check a Kubernetes cluster for high-availability best practices and flag deployments that could be disrupted by a node upgrade, before you run one.

[![CI](https://github.com/jborusu1991/kubeclear/actions/workflows/ci.yml/badge.svg)](https://github.com/jborusu1991/kubeclear/actions/workflows/ci.yml)
[![SAST](https://github.com/jborusu1991/kubeclear/actions/workflows/sast.yml/badge.svg)](https://github.com/jborusu1991/kubeclear/actions/workflows/sast.yml)
[![Trivy](https://github.com/jborusu1991/kubeclear/actions/workflows/trivy.yml/badge.svg)](https://github.com/jborusu1991/kubeclear/actions/workflows/trivy.yml)
[![SBOM](https://github.com/jborusu1991/kubeclear/actions/workflows/sbom.yml/badge.svg)](https://github.com/jborusu1991/kubeclear/actions/workflows/sbom.yml)

## What it does

`kubeclear` connects to a cluster via your kubeconfig, reads Deployments in the namespaces you specify, and runs two independent checks against each one:

- **Topology spread check** (`--topology-spread-check`) — compares each deployment's *actual* pod placement against both `kubernetes.io/hostname` and `topology.kubernetes.io/zone`. It uses the `maxSkew` from the deployment's own `topologySpreadConstraints` when one is configured for a key (falling back to `podAntiAffinity` — a `required` rule implies strict separation, a `preferred` rule falls back to the default tolerance), and a default skew tolerance of `1` otherwise. A deployment is flagged as violated only when it's unevenly spread on **both** node and zone dimensions — i.e. a genuine single point of failure risk, not just a soft imbalance on one axis.
- **Node upgrade precheck** (`--upgrade-precheck`) — looks up the PodDisruptionBudget covering each deployment's pods and reports whether draining 1 or 2 nodes at once (see `NUMBER_OF_NODES_UPGRADE`) would exceed the PDB's currently allowed disruptions, i.e. whether it would actually **block** a node drain during a cluster upgrade.

Both checks report which node(s) and zone(s) the deployment's pods are currently running on.

The full list of HA guardrails this project is working toward (replica counts, PriorityClass, probes, graceful termination, etc.) is tracked in [checks.md](checks.md) — topology spread and PDB-based upgrade prechecks are implemented so far.

## Installation

Requires Python 3.12+ and [Poetry](https://python-poetry.org/).

```bash
poetry install
```

This installs `kubeclear` as a console script inside the Poetry-managed virtualenv.

### Docker

```bash
docker build -t kubeclear .
docker run --rm -v ~/.kube/config:/home/kubeclear/.kube/config:ro kubeclear --namespaces default --topology-spread-check
```

## Usage

```bash
poetry run kubeclear --namespaces <namespace> [<namespace> ...] [options]
```

| Flag | Description |
|---|---|
| `--namespaces`, `-n` | One or more namespaces to check (required) |
| `--topology-spread-check` | Run the topology spread check |
| `--upgrade-precheck` | Run the PDB-based node upgrade precheck |
| `--output {table,csv}` | Output format (default: `table`, printed to stdout) |
| `--output-file` | File to write to when `--output csv` is used (default: `kubeclear_report.csv`) |

Example:

```bash
poetry run kubeclear -n default kube-system --topology-spread-check --upgrade-precheck --output csv
```

Runs both checks against the `default` and `kube-system` namespaces and writes both reports to `kubeclear_report.csv`, one section per check, separated by a `----- <Report> -----` header row.

## Configuration

- **Kubeconfig**: standard kubeconfig resolution — the `KUBECONFIG` env var if set, otherwise `~/.kube/config`. Works with EKS clusters out of the box via the `exec` credential plugin (requires the `aws` CLI or `aws-iam-authenticator` on `PATH`).
- **`NUMBER_OF_NODES_UPGRADE`** (env var, default `2`): how many nodes the upgrade precheck assumes get drained simultaneously when checking for PDB blocking.

## Development

```bash
poetry install
poetry run pytest --cov=kubeclear --cov-report=term-missing
```

Tests don't require a live cluster — `tests/conftest.py` points `KUBECONFIG` at `tests/dummy_kubeconfig.yaml`, and individual API calls are mocked with `monkeypatch` where needed.

## CI/CD

- **`ci.yml`** — runs the test suite with coverage and JUnit reporting, and builds the sdist/wheel.
- **`docker-build-push.yml`** — builds and pushes the Docker image.
- **`sast.yml`** — CodeQL static analysis for Python.
- **`trivy.yml`** — Trivy container image scan; uploads SARIF to the Security tab and gates the build on fixable Critical/High vulnerabilities.
- **`sbom.yml`** — generates source (CycloneDX) and image (SPDX) SBOMs as build artifacts.
