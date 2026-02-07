# nbac-worker

Cloudflare worker for archetype classification using NBAC (multinomial Naive Bayes).

[Overview](#overview) |
[Project Structure](#project-structure) |
[`/nbac` Endpoint](#nbac-endpoint) |
[Setup and Deployment](#setup-and-deployment) |
[License](#license)

## Overview

NBAC (Naive Bayes Archetype Classification) identifies the most likely archetypes for a given decklist based on observed card counts from a labeled corpus. This project uses Cloudflare Workers + D1 to serve low-latency inference.

## Project Structure

<!-- Create a file tree with comments -->
```sh
.
├── src/
│   ├── nbac/ # NBAC library (training + binary artifacts + scoring).
│   │   ├── __init__.py
│   │   ├── archetypes.py
│   │   ├── binary.py
│   │   ├── model.py
│   │   ├── score.py
│   │   ├── train.py
│   │   └── postgres.py
│   ├── router.py # A zero-dependency request router.
│   └── worker.py # The main Cloudflare worker script.
├── .env-example
├── build.py # Build script for updating Cloudflare D1 NBAC artifacts.
├── pyproject.toml
└── wrangler.toml # Configuration file for Cloudflare Workers.
```

## `/nbac` Endpoint

### Request

To classify the archetype of a decklist, send a POST request to the `/nbac` endpoint with a JSON body containing either:

- a list of card names (presence-only input), or
- a list of objects with `name` and `quantity`.

#### URL

```http
POST https://ml.videreproject.com/nbac?format=modern # or another format
```

#### Query Parameters

- `format` (required): `standard|modern|pioneer|vintage|legacy|pauper`
- `explain` (optional): enable explainability output (`0`/`1`, default `0`)
- `explain_method` (optional): `lift|contrib` (default `lift`)
- `explain_top` (optional): number of top archetypes to explain (default `1`, max `25`)
- `explain_n` (optional): number of top cards per explained archetype (default `12`, max `25`)

#### Headers

```http
Content-Type: application/json
```

#### Body

The request body must be a valid JSON array.

For example:

```json
// Presence-only input
[
  "Agatha's Soul Cauldron",
  "Ancient Stirrings",
  "Basking Broodscale",
  "Mox Opal",
  "Urza's Saga"
]

// Quantity input
[
  {"name": "Agatha's Soul Cauldron", "quantity": 1},
  {"name": "Ancient Stirrings", "quantity": 4},
  {"name": "Urza's Saga", "quantity": 4}
]
```

### Response

The response is a JSON object containing the top archetypes and their posterior probabilities.

#### Success Response

```json
{
  "meta": {
    // Indicates which database type was used. Currently, only D1 is supported.
    "database": "D1",
    // The Cloudflare worker backend used to process the request.
    "backend": "v3-prod",
    // The total SQL execution time in milliseconds.
    "exec_ms": 5.758,
    // The number of rows read/scanned by the query.
    "read_count": 2742,
    // Which NBAC model was used based on input payload shape.
    "model": "counts"
  },
  // Posterior probabilities for each archetype.
  "data": {
    "Basking Broodscale Combo": 0.84,
    "Eldrazi": 0.09,
    "Affinity": 0.03
  },
  // Optional per-card evidence (enabled with `explain=1`).
  "explain": {
    // Evidence method used: "lift" prefers background-relative lift when available,
    // otherwise falls back to "contrib".
    "method": "lift",
    // Number of archetypes explained.
    "top": 1,
    // Number of cards per archetype.
    "n": 12,
    "archetypes": {
      "Basking Broodscale Combo": [
        {"card": "Urza's Saga", "quantity": 4, "score": 1.23456789},
        {"card": "Mox Opal", "quantity": 1, "score": 0.98765432}
      ]
    }
  }
}
```

### Error Response

#### Missing `format` parameter

When the `format` URL parameter is missing, the response will be:

```json
{
  "error": "Missing Parameter",
  "message": "The 'format' parameter is required."
}
```

If the `format` parameter provided is invalid, the response will be:

```json
{
  "error": "Invalid Parameter",
  "message": "The 'format' parameter '...' is not supported."
}
```

#### Invalid JSON

In cases where the request body is not a valid JSON array (e.g., the body is malformed or an object is provided instead), the response will be:

```json
{
  "error": "Invalid JSON",
  "message": "The request body must be a valid JSON array."
}
```

#### Insufficient Cards

If the request body contains fewer than two cards, the response will be:

```json
{
  "error": "Invalid JSON",
  "message": "The request body must contain at least two cards."
}
```

## Setup and Deployment

### Install Tools

1. **Install Wrangler**: Install the Wrangler CLI tool.

```bash
npm install -g @cloudflare/wrangler@^3.68.0
```

2. **Install UV CLI**: Install the UV CLI tool to manage dependencies.

```bash
npm install -g @cloudflare/uv@latest
```

### Configure and Set Up

1. **Configure Wrangler**: Update the [wrangler.toml](/wrangler.toml) file with your Cloudflare account details.

2. **Set Up Environment Variables**: Create a `.env` file in the root directory based on the provided `.env-example` file and fill in your Cloudflare credentials.

### Install Dependencies

Use the [UV CLI](https://docs.astral.sh/uv/getting-started/installation/) to install the required dependencies.

```bash
uv install
```

### Setup Database Tunnel

To run the build script locally, you must connect to the production database via a Cloudflare Tunnel bridge.

1.  **Install `cloudflared`**: Follow the [official instructions](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) or use a package manager.

2.  **Start the Bridge**: Run the following command to forward the remote database to your local port `5433`.

    ```bash
    # Forward the remote Postgres service to localhost:5433
    cloudflared access tcp --hostname db1.videreproject.com --url localhost:5433
    ```

    *Note: For more infrastructure details, see the [`videre-project/mtgo-db`](https://github.com/videre-project/mtgo-db) repository.*

3.  **Update `.env`**: Ensure your `.env` file points to this local port (see `.env-example`).

### Build and Deploy

1. **Build NBAC Artifacts**: Run the build script to update Cloudflare D1 with the latest NBAC artifacts for each format.

```bash
uv run build.py
```

2. **Local Development**: Test the worker locally using Wrangler.

```bash
npx wrangler dev
```

3. **Deploy**: Deploy the worker using Wrangler.

```bash
npx wrangler deploy
```

## License

This project is licensed under the Apache-2.0 License. See the [LICENSE](/LICENSE) file for more details.
