 # The TNA API: A Comprehensive Developer's Manual

## 1\. Introduction & Getting Started

This manual provides the definitive technical reference for The National Archives (TNA) of the UK's Discovery API. It is designed to be a comprehensive, all-encompassing resource for software developers and AI agents building applications that interact with TNA's vast collection of archival metadata. The information herein is synthesized from all publicly available documentation, technical specifications, and operational data to provide a single, authoritative guide.

### 1.1 Purpose of the API: Unlocking a Millennium of Records

The TNA Discovery API serves as the primary programmatic gateway to the UK's national archival collection. It is designed to maximize access to the information held in The National Archives' Discovery service. The Discovery service contains descriptions for over 35 million records held not only by The National Archives but also by more than 2,500 other archives and institutions across the United Kingdom and around the world. The API empowers developers to build sophisticated applications for academic research, data analysis, genealogical exploration, and educational platforms by allowing them to programmatically query the search engine and database.

The API returns data in either JSON or XML format, allowing for flexible integration with modern application stacks. Its core function is to allow programmatic querying of record descriptions, titles, and associated metadata. It is important to note that the API provides access to the *catalogue descriptions* of records, not the full-text content of the records themselves, even for those that have been digitized.

While TNA documentation refers to the service as a "beta" offering, analysis of its public development activity indicates a state of functional stability. The primary public code repository associated with the API has not seen significant updates for a considerable period. This suggests that developers should treat the API as a stable, mature service that is in a maintenance phase rather than one undergoing active feature development. The functionality described in this manual is therefore considered complete and reliable for production use, but developers should not anticipate the release of new features or major version changes in the near future.

### 1.2 API Access and Authentication: A Manual Approach

The TNA Discovery API employs an IP-based allowlisting mechanism for authentication, which is a departure from the self-service API key or OAuth 2.0 systems common to many modern APIs. This method requires direct communication with The National Archives to gain access.

The process for obtaining access is as follows:

1.  **Initiate Contact:** The developer or organization must send a formal request for API access via email to The National Archives at `discovery@nationalarchives.gov.uk`.
2.  **Provide Static IP Address:** The request must include the static public IP address(es) from which all API requests will originate. The API service grants access on a per-IP basis, so a stable, non-dynamic IP address is required for any server or service that will communicate with the API.
3.  **State Your Use Case:** You should include your intended use case and API usage requirements in the request.
4.  **Await Approval:** TNA staff will review the request. Upon approval, the provided IP address will be added to an access control list, granting it permission to make calls to the API endpoints.

Once an IP address is allowlisted, no further authentication is required within the API calls themselves. Requests do not need to include an `Authorization` header or an API key as a query parameter. Authentication is handled entirely at the network level based on the source IP of the request.

This manual, IP-centric authentication model indicates that the API was likely designed for a controlled number of institutional partners, academic projects, or specific vetted applications rather than for mass, anonymous consumption. Developers should factor the potential for a manual approval delay into their project timelines and ensure their deployment architecture can support a static IP address.

### 1.3 Base URL and Versioning

All API requests must be directed to the following base URL. All endpoint paths documented in this manual are relative to this base.

  * **Base URL:** `https://discovery.nationalarchives.gov.uk/API`

The API employs a URI path versioning scheme, with the current version being `v1`. To ensure stability and forward compatibility, developers must include the version number in the path for all API calls (e.g., `/v1/`). The API may also support unversioned endpoints for backward compatibility.

## 2\. Core Concepts

A foundational understanding of archival principles and TNA's data organization is essential for effective use of the Discovery API. This section clarifies the API's scope and defines the key data structures and concepts that underpin the system.

### 2.1 Discovery API vs. Other Government APIs

This manual is exclusively focused on **The National Archives Discovery API**. It is critical to distinguish this service from other related but distinct APIs provided by the UK government and other national bodies:

  * **Legislation API:** Hosted at `legislation.gov.uk`, this API provides programmatic access to UK statutes, statutory instruments, and other legal documents.
  * **GOV.UK Content API:** This service exposes content and metadata for pages hosted on the main `www.gov.uk` website.
  * **Find Case Law API:** A specialized API for accessing court judgments and tribunal decisions from the Find Case Law service.
  * **US National Archives (NARA) API:** The API for the United States' national archival institution. It is a completely separate system with its own authentication (API key-based), endpoints, and data models.

### 2.2 Data Structure: The Archival Hierarchy

The data within the Discovery catalogue is not a flat list of documents. Instead, it is organized into a deep hierarchy that reflects the provenance of the records—that is, their origin and organizational context. This structure adheres to the International Standard for Archival Description (ISAD(G)). Understanding this hierarchy is fundamental to interpreting API responses and navigating relationships between records.

The levels of the hierarchy, from broadest to most specific, are:

1.  **Department:** The highest level, typically representing a government department, agency, or other major body that created the records.
2.  **Division:** An administrative sub-section of a department.
3.  **Series:** The main grouping of records that share a common function, subject, or record-keeping system.
4.  **Sub-series / Sub sub-series:** More granular groupings within a series, used to further refine the organization.
5.  **Piece:** A logical or physical unit of records. A piece is not a single sheet of paper; it is typically a box, a large volume, a file, or a folder containing multiple documents.
6.  **Item:** The most granular level of description, representing a single entity within a piece, such as a letter, a photograph, a map, or a single report.

Each record returned by the API will exist at one of these levels, and its metadata will often include information about its parent and child records, allowing an application to reconstruct its context.

### 2.3 Fundamental Data Concepts

The API's data models are built around several core archival concepts:

  * **Information Asset:** In TNA's official terminology, an Information Asset is "a body of information, defined and managed as a single unit so it can be understood, shared, protected and exploited efficiently". In the context of the API, this typically refers to a high-level, describable entity, such as the entire body of work from a specific creator or a significant collection. The `FileAuthorityViewModel` object exposed by the API appears to be the technical representation of an Information Asset.
  * **Record:** A record is the fundamental unit of the archive. It refers to any information created, received, and maintained as evidence and information by an organization or person. Within the API, a "record" is a catalogue entry at any level of the archival hierarchy (Item, Piece, Series, etc.).
  * **Creator:** The person, family, or organization that created, accumulated, or maintained a body of records. Creators are distinct from the records themselves and are a primary access point for research. The API provides functionality to search for records associated with specific creators and to retrieve detailed information about the creators themselves.

### 2.4 Identifier System

The API uses several types of identifiers to reference records and other entities.

  * **IAID (Information Asset Identifier):** Unique identifiers for records within the Discovery system.
  * **Archival Reference Code / Citable Reference:** This is the primary human-readable identifier for a record. It is a unique code that reflects the record's position within the archival hierarchy (e.g., `WO 95/26`) and is the standard way of citing archival material.
  * **Internal Database Identifiers:** The API also uses internal system identifiers (e.g., `C193`, `C9134`, `A12345`) to uniquely identify records, information assets, and other objects. These are typically used in API calls to retrieve the details of a specific object.
  * **ARCHON codes:** Identifiers for archives and repositories.
  * **PRONOM Unique Identifier (PUID):** While not directly exposed in the record metadata of the Discovery API, PUIDs are a core part of TNA's wider digital preservation infrastructure. A PUID is a persistent, unique, and unambiguous identifier for a specific file format (e.g., PDF 1.4, JPEG).

## 3\. API Endpoints: In-Depth Reference

This section provides a detailed reference for all API endpoints.

### 3.1 File Authority Endpoints

#### GET /fileauthorities/v1/details/{id}

**Description:** Retrieves the detailed information for a specific "File Authority" or Information Asset, which typically represents a record creator, such as a person or an organization.

  * **HTTP Method:** `GET`

**Parameters**

| Parameter Name | Data Type | Description | Required/Optional | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `string` | The unique identifier for the Information Asset. This value is case-sensitive. | Required | `C193` / `A12345` |

**Example Request**

```bash
curl -X GET "https://discovery.nationalarchives.gov.uk/API/fileauthorities/v1/details/C193" \
     -H "Accept: application/json"
```

**Example JSON Response**

```json
{
  "AuthorityName": "Shakespeare, William",
  "BiographyHistory": "William Shakespeare (1564-1616) was an English poet, playwright, and actor, widely regarded as the greatest writer in the English language and the world's pre-eminent dramatist.",
  "Epithet": "Dramatist and poet",
  "Forenames": "William",
  "IsAuthorityRecord": true,
  "IsPublic": true,
  "Name": "Shakespeare, William",
  "NameForm": "Person",
  "SortName": "Shakespeare, William",
  "Sources": "Sources of Authority: Oxford Dictionary of National Biography.",
  "SubjectType": "Person",
  "Title": "Mr"
}
```

**Response Messages**

  * **200:** OK - Successfully retrieved file authority details
  * **204:** No content - Record not found
  * **400:** Bad request - Invalid parameters
  * **404:** Not found - Endpoint not available
  * **500:** Internal Server Error

#### GET /fileauthorities/v1/collection/{type}

**Description:** Get file authority records collection.

  * **HTTP Method:** `GET`

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `type` | `string` | File authority record type (Business/Family/Manor/Organisation/Person) | Yes | "Person" |
| `direction` | `string` | Paging direction (NEXT/PREV) | No | "NEXT" |
| `includeCursor` | `boolean` | Include or exclude cursor in results | No | `true` |
| `batchStartRecordId` | `string` | Record ID to start next page | No | "A12345" |
| `batchStartMark` | `string` | SortKey value to start next page | No | "smith\_john" |
| `limit` | `integer` | Number of records returned (1-500, default 30) | No | 50 |

*(Table data sourced from)*

**Example Request**

```bash
curl -X GET "https://discovery.nationalarchives.gov.uk/API/fileauthorities/v1/collection/Person?limit=10&direction=NEXT" \
     -H "Accept: application/json"
```

### 3.2 Records Endpoints

#### GET /records/v1/details/{id}

**Description:** Retrieves the full descriptive metadata for a single archival record using its unique identifier.

  * **HTTP Method:** `GET`

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `string` | The unique internal identifier for the record. This value is case-sensitive. | Yes | `C9134` / `C123456` |

**Example Request**

```bash
curl -X GET "https://discovery.nationalarchives.gov.uk/API/records/v1/details/C9134" \
     -H "Accept: application/json"
```

**Example JSON Response**

```json
{
  "Id": "C9134",
  "Title": "1st Battalion, The Queen's (Royal West Surrey Regiment)",
  "CitableReference": "WO 95/26",
  "CoveringDates": "1914 August - 1919 March",
  "ScopeContent": {
    "Description": "This piece contains the war diary of the 1st Battalion of The Queen's (Royal West Surrey Regiment) for the period of August 1914 to March 1919. It details daily operations, movements, casualties, and notable events during their service on the Western Front."
  },
  "Digitised": true,
  "ClosureStatus": "Open Document, Open Description",
  "CatalogueLevel": 6,
  "Source": "TNA",
  "heldBy": "The National Archives, Kew",
  "level": "Piece",
  "legalStatus": "Public Record(s)"
}
```

#### GET /records/v1/collection/{reference}

**Description:** Get collection of records with the same citable reference.

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `reference` | `string` | Citable reference | Yes | "WO 32" |

*(Table data sourced from)*

#### GET /records/v1/children/{parentId}

**Description:** Get collection of related records within one cataloguing level.

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `parentId` | `string` | Parent record ID | Yes | "C123456" |

*(Table data sourced from)*

#### GET /records/v1/context/{id}

**Description:** Get context of the record (hierarchical structure).

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `string` | Record ID | Yes | "C123456" |

*(Table data sourced from)*

### 3.3 Repository Endpoints

#### GET /repository/v1/details/{id}

**Description:** Get archive details by archive record ID.

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `string` | Archive record ID | Yes | "A65" |

*(Table data sourced from)*

#### GET /repository/v1/collection

**Description:** Get Archon records collection.

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `limit` | `integer` | Number of records (1-500, default 30) | No | 50 |

*(Table data sourced from)*

### 3.4 Search Endpoints

#### GET /search/v1/records

**Description:** Performs a search across the Discovery catalogue.

  * **HTTP Method:** `GET`

**Parameters**

| Parameter | Data Type | Description | Required | Example Value |
| :--- | :--- | :--- | :--- | :--- |
| `sps.searchQuery` | `string` | Search query with boolean expressions. | No | "war AND diary" |
| `sps.dateFrom` | `date-time` | Record covering date start (ISO 8601). | No | "1914-01-01T00:00:00" |
| `sps.dateTo` | `date-time` | Record covering date end (ISO 8601). | No | "1918-12-31T23:59:59" |
| `sps.departments` | `string[]` | TNA department filter codes. | No | `["WO", "ADM"]` |
| `sps.catalogueLevels` | `string[]` | Catalogue level filter. | No | `["Level6", "Level7"]` |
| `sps.closureStatuses` | `string[]` | Closure status codes (O/C/R/P). | No | `["O"]` |
| `sps.heldByCode` | `string` | Repository filter (ALL/TNA/OTH). | No | "TNA" |
| `sps.online` | `boolean` | If `true`, returns only records with a downloadable version. | No | `true` |
| `sps.resultsPageSize` | `integer` | Results per page (0-1000, default 15). | No | 100 |
| `sps.page` | `integer` | Page number (0-100), for standard pagination. | No | 0 |
| `sps.sortByOption` | `string` | Sort option. | No | "RELEVANCE" |

*(Table data sourced from)*

**Sort Options**

  * RELEVANCE
  * REFERENCE\_ASCENDING
  * DATE\_ASCENDING
  * DATE\_DESCENDING
  * TITLE\_ASCENDING
  * TITLE\_DESCENDING

*(List sourced from)*

**Example Request**

```bash
curl -X GET "https://discovery.nationalarchives.gov.uk/API/search/v1/records?sps.searchQuery=churchill&sps.heldByCode=TNA&sps.resultsPageSize=50" \
     -H "Accept: application/json"
```

**Example JSON Response**

```json
{
  "Records": [
    {
      "Id": "C123456",
      "Reference": "PREM 1/123",
      "Title": "Prime Minister's Papers: Churchill Correspondence",
      "CoveringDates": "1940-1945",
      "Description": "Personal correspondence of Winston Churchill",
      "ClosureStatus": "Open",
      "Score": 95.7
    }
  ],
  "Count": 1542,
  "NextBatchMark": "eyJzb3J0IjpbeyJfaWQi..."
}
```

## 4\. Data Models & Schemas

### 4.1 The Record Model

This model represents a single entry in the archival catalogue.

| Field | Data Type | Description |
| :--- | :--- | :--- |
| `id` / `Id` | `string` | The internal unique identifier for the record. |
| `title` / `Title` | `string` | The official title of the record. |
| `reference` / `CitableReference` | `string` | The human-readable archival reference code (e.g., `WO 95/26`). |
| `description` / `ScopeContent` | `string` / `object` | A detailed description of the record's scope and content. |
| `dateRange` / `CoveringDates` | `string` | The covering dates for the record's content (e.g., "1914-1918"). |
| `CoveringFromDate` | `integer` | Start date (numeric). |
| `CoveringToDate` | `integer` | End date (numeric). |
| `level` / `CatalogueLevel` | `string` / `integer` | The record's level in the archival hierarchy (e.g., "Piece", 6). |
| `heldBy` / `Source` | `string` | The name of the institution holding the record or a data source identifier. |
| `legalStatus` | `string` | The legal status of the record (e.g., "Public Record(s)"). |
| `closureStatus` / `ClosureStatus` | `string` | The access status of the record (e.g., "Open", "Open Document, Open Description"). |
| `ClosureCode` | `string` | Closure reason code. |
| `Digitised` | `boolean` | A flag indicating if the record has been digitized. |
| `hierarchy` | `Array[Object]` | An array of parent objects showing the record's context within the archive. |

### 4.2 The Information Asset / File Authority Model

This data model represents a creator of records, such as a person, family, or organization.

| Field | Data Type | Description |
| :--- | :--- | :--- |
| `AuthorityName` | `string` | The primary display name of the authority. |
| `BiographyHistory` | `string` | A detailed narrative biography or history of the authority. |
| `SubjectType` | `string` | The type of authority (e.g., "Person", "Family", "Business"). |
| `Epithet` | `string` | A descriptive phrase or title (e.g., "Dramatist and poet"). |
| `Forenames` | `string` | The first name(s) of the person. |
| `Title` | `string` | A personal title, such as "Mr", "Sir", or "Dr". |
| `Name` | `string` | The full name of the authority. |
| `NameForm` | `string` | The form of the name (e.g., "Person", "Organisation"). |
| `SortName` | `string` | The name formatted for alphabetical sorting. |
| `Sources` | `string` | A text field listing sources used for the authority information. |
| `Places` | `Array[Place]` | An array of associated places. |
| `IsPublic` | `boolean` | A flag indicating if the record is public. |
| `IsAuthorityRecord` | `boolean` | A flag indicating if this is a formal authority record. |

### 4.3 The Place Object

| Field | Data Type | Description |
| :--- | :--- | :--- |
| `Country` | `string` | Country name |
| `County` | `string` | County name |
| `PlaceName` | `string` | Specific place name |
| `StartDate` | `integer` | Start date association |
| `EndDate` | `integer` | End date association |
| `Grid` | `string` | Grid reference |

*(Table data sourced from)*

## 5\. Search & Filtering

### 5.1 Search Syntax

The primary search functionality is controlled via the `sps.searchQuery` query parameter. This parameter accepts a string containing keywords and operators to define the search criteria.

| Operator | Example | Description |
| :--- | :--- | :--- |
| `AND` | `turing AND enigma` | Returns records containing both "turing" and "enigma". This is often the default behavior. |
| `OR` | `spitfire OR hurricane` | Returns records containing either "spitfire" or "hurricane". |
| `NOT` | `lancaster NOT avro` | Returns records containing "lancaster" but excludes any that also contain "avro". |
| `"` `"` | `"Domesday Book"` | Performs an exact phrase search. Returns records where "Domesday" is immediately followed by "Book". |
| `*` | `parliamen*` | Acts as a wildcard (suffix only). Returns records containing terms that start with "parliamen". |
| `( )` | `(spitfire OR hurricane) AND dowding` | Groups expressions to control the order of operations. |

### 5.2 Field-Specific Searching

You can restrict searches to specific fields using the `sps.searchRestrictionFields` parameter.

**Available Fields:**

  * title
  * description
  * reference
  * people
  * places
  * subjects

*(List sourced from)*

### 5.3 Filtering Options

**Date Filtering:**
Use `sps.dateFrom` and `sps.dateTo` with ISO 8601 date-time formats.
`sps.dateFrom=1939-09-01T00:00:00`
`sps.dateTo=1945-05-08T23:59:59`

**Department Filtering (TNA records only):**
Use an array of department codes.
`sps.departments=["WO", "ADM", "AIR"]`

**Closure Status Filtering:**

  * `O` - Open
  * `C` - Closed
  * `R` - Retained
  * `P` - Pending review

*(List sourced from)*

**Repository Filtering:**

  * `ALL` - All repositories
  * `TNA` - The National Archives only
  * `OTH` - Other archives only

*(List sourced from)*

### 5.4 Pagination

The API supports two pagination methods:

**Standard Pagination:**
Controlled by two query parameters:

  * `sps.page`: An integer specifying which page of results to return. The first page is `0`.
  * `sps.resultsPageSize`: An integer specifying the number of results per page.

**Deep Pagination (Cursor-based):**
For iterating through very large result sets, a cursor-based approach is available.

  * `sps.batchStartMark=*` (For the first request)
  * `sps.batchStartMark=eyJzb3J0...` (Use the `NextBatchMark` value from the previous response for subsequent requests)

### 5.5 Practical Search Examples

#### Simple Keyword Search

To search for records related to the Battle of Trafalgar:

```
https://discovery.nationalarchives.gov.uk/API/search/v1/records?sps.searchQuery=trafalgar
```

#### Exact Phrase Search

To find the specific will of William Shakespeare:

```
https://discovery.nationalarchives.gov.uk/API/search/v1/records?sps.searchQuery="will of william shakespeare"
```

#### Complex Boolean Search with Filtering

To find records from The National Archives (`TNA`) between 1940 and 1942 related to Alan Turing but not mentioning Bletchley Park:

```
https://discovery.nationalarchives.gov.uk/API/search/v1/records?sps.searchQuery=turing NOT "bletchley park"&sps.dateFrom=1940-01-01T00:00:00&sps.dateTo=1942-12-31T23:59:59&sps.heldByCode=TNA
```

## 6\. Rate Limiting, Errors, & Best Practices

### 6.1 Rate Limits

TNA provides guidelines regarding rate limits. To ensure robust compliance, developers should adhere to the most restrictive limits.

  * **Primary Guideline:** No more than **1 request per second**, with a total of no more than **3,000 API calls per day**.
  * **Fair Use Policy:** A separate policy for automated traffic specifies a limit of **3,000 requests in any 5-minute period**.

**Best Practice:** Developers should implement client-side throttling in their applications to strictly adhere to the **1 request per second** limit. This is the most conservative approach and guarantees compliance.

If an application exceeds these limits, its source IP address will be temporarily blocked from accessing the API. The block is automatically lifted once the rolling average request rate falls below the permitted threshold.

### 6.2 Error Handling

The API uses standard HTTP status codes to indicate the outcome of a request. Client applications must be designed to handle these codes gracefully.

| HTTP Status Code | Meaning | Likely Cause | Recommended Client Action |
| :--- | :--- | :--- | :--- |
| `200 OK` | OK | The request was successful. | Process the response body. |
| `204 No Content` | No Content | Record not found. | Handle as an empty or "not found" result. |
| `400 Bad Request` | Bad Request | Invalid parameters or malformed request syntax. | Log the error, validate request syntax against the manual, do not retry without modification. |
| `401 Unauthorized` | Unauthorized | IP address is not on the TNA allowlist. | Verify the application's IP address has been registered with TNA. |
| `403 Forbidden` | Forbidden | Access is denied, likely due to allowlist issues. | Verify that the application's public-facing IP address has been successfully registered. |
| `404 Not Found` | Not Found | The requested endpoint or resource could not be found. | Check for typographical errors in the endpoint path. Treat a missing record ID as a valid "not found" state. |
| `429 Too Many Requests` | Too Many Requests | The application has exceeded the rate limits. | Immediately stop sending requests and implement an exponential backoff strategy. |
| `500 Internal Server Error` | Internal Server Error | An unexpected error occurred on TNA's servers. | This is a server-side issue. Wait a short period before retrying. Report persistent errors to TNA support. |
| `503 Service Unavailable` | Service Unavailable | The API is temporarily unavailable (e.g., maintenance). | Treat similarly to a 500 error; implement a retry mechanism with exponential backoff. |

**Error Response Format**

```json
{
  "error": {
    "code": "400",
    "message": "Invalid search syntax",
    "details": "Boolean operator 'XOR' is not supported"
  }
}
```

### 6.3 Best Practices

  * **Construct Efficient Queries:** Make search queries as specific as possible using `AND`, `NOT`, and filters to reduce data transfer and server load.
  * **Implement Client-Side Throttling:** Proactively manage your request rate to stay well within the 1 request/second limit.
  * **Set a Descriptive User-Agent:** It is a strong best practice to include a `User-Agent` header in all API requests (e.g., `ApplicationName/Version (contact-url-or-email)`). This helps TNA identify your application's traffic.
  * **Cache Responses:** Cache data where appropriate for your use case, such as static repository information, to reduce redundant calls.
  * **Adhere to Licensing:** All information accessed via the API is provided under the terms of the Open Government Licence. Ensure your application's use of the data is compliant.
  * **Handle Data Responsibly:** Always validate response data before processing and handle empty result sets gracefully.

## 7\. Practical Code Examples

### 7.1 Python (`requests` library)

#### Making an Authenticated API Call and Searching

This example searches for records related to "Bletchley Park" and prints the titles of the first page of results.

```python
import requests
import time
import json

class TNAAPIClient:
    def __init__(self, base_url="https://discovery.nationalarchives.gov.uk/API"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'MyTNAApp/1.0 (contact@example.com)'
        })
    
    def make_request(self, endpoint, params=None):
        """Make a rate-limited request to the TNA API"""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            # Your server's IP must be allowlisted by TNA for this to work.
            response = self.session.get(url, params=params, timeout=10)
            
            # Raise an exception for bad status codes (4xx or 5xx).
            response.raise_for_status()
            
            # Rate limiting: 1 request per second
            time.sleep(1)
            
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except requests.exceptions.RequestException as err:
            print(f"An error occurred: {err}")
        
        return None

def search_records(client, query, page=0, page_size=10):
    """Searches for records in the TNA Discovery API."""
    endpoint = "search/v1/records"
    
    params = {
        'sps.searchQuery': query,
        'sps.page': page,
        'sps.resultsPageSize': page_size
    }

    return client.make_request(endpoint, params=params)

if __name__ == "__main__":
    tna_client = TNAAPIClient()
    search_query = '"Bletchley Park" AND ULTRA'
    results = search_records(tna_client, search_query)

    if results and "Records" in results:
        print(f"Found {results.get('Count', 0)} records for '{search_query}'.\n")
        for record in results["Records"]:
            print(f"  - [{record.get('Reference', 'N/A')}] {record.get('Title', 'N/A')}")
```

#### Retrieving a Single Record by ID

```python
def get_record_details(client, record_id):
    """Retrieves the full details for a single record by its ID."""
    endpoint = f"records/v1/details/{record_id}"
    return client.make_request(endpoint)

if __name__ == "__main__":
    tna_client = TNAAPIClient()
    record_details = get_record_details(tna_client, "C9134") # Example ID
    if record_details:
        print("\n--- Record Details ---")
        print(json.dumps(record_details, indent=2))
```

### 7.2 JavaScript (`axios` for Node.js)

#### Making an Authenticated API Call and Searching

This example uses `axios` in a Node.js environment to search for records.

```javascript
const axios = require('axios');

const BASE_URL = 'https://discovery.nationalarchives.gov.uk/API';
let lastRequestTime = 0;

/**
 * Ensures a delay of at least 1 second between API calls.
 */
async function rateLimit() {
  const now = Date.now();
  const timeSinceLastRequest = now - lastRequestTime;
  if (timeSinceLastRequest < 1000) {
    await new Promise(resolve => setTimeout(resolve, 1000 - timeSinceLastRequest));
  }
  lastRequestTime = Date.now();
}

/**
 * Searches for records in the TNA Discovery API.
 * @param {string} query - The search query string.
 * @param {number} page - The page number to retrieve.
 * @param {number} pageSize - The number of results per page.
 * @returns {Promise<object|null>} The JSON response from the API, or null on error.
 */
async function searchRecords(query, page = 0, pageSize = 10) {
  await rateLimit();
  const endpoint = `${BASE_URL}/search/v1/records`;

  const params = {
    'sps.searchQuery': query,
    'sps.page': page,
    'sps.resultsPageSize': pageSize,
  };

  const headers = {
    'User-Agent': 'MyTNAApp/1.0 (contact@example.com)',
  };

  try {
    // Your server's IP must be allowlisted by TNA for this to work.
    const response = await axios.get(endpoint, { params, headers, timeout: 10000 });
    return response.data;
  } catch (error) {
    if (error.response) {
      console.error(`Error: ${error.response.status} - ${error.response.statusText}`);
    } else {
      console.error('Error:', error.message);
    }
    return null;
  }
}

(async () => {
  const searchQuery = '"enigma machine"';
  const results = await searchRecords(searchQuery);

  if (results && results.Records) {
    console.log(`Found ${results.Count} records for '${searchQuery}'.\n`);
    results.Records.forEach(record => {
      console.log(`  - [${record.Reference}] ${record.Title}`);
    });
  }
})();
```

#### Retrieving a Single Record by ID

```javascript
/**
 * Retrieves the full details for a single record by its ID.
 * @param {string} recordId - The unique identifier of the record.
 * @returns {Promise<object|null>} The JSON response from the API, or null on error.
 */
async function getRecordDetails(recordId) {
  await rateLimit();
  const endpoint = `${BASE_URL}/records/v1/details/${recordId}`;
  
  const headers = {
    'User-Agent': 'MyTNAApp/1.0 (contact@example.com)',
  };

  try {
    const response = await axios.get(endpoint, { headers, timeout: 10000 });
    return response.data;
  } catch (error) {
    console.error(`Failed to retrieve details for record ${recordId}:`, error.message);
    return null;
  }
}

(async () => {
  // Example usage:
  const recordDetails = await getRecordDetails('C9134'); // Example ID
  if (recordDetails) {
    console.log('\n--- Record Details ---');
    console.log(JSON.stringify(recordDetails, null, 2));
  }
})();
```