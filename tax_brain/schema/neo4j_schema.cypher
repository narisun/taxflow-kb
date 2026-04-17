// =============================================================================
// TaxFlow AI — IRS Knowledge Base — Neo4j Schema
// Layer 1: MeF Business Rules Graph
// Run with: cypher-shell -u neo4j -p <password> -f neo4j_schema.cypher
// =============================================================================

// ─── Uniqueness Constraints ───────────────────────────────────────────────────
// Note: NODE KEY (uniqueness + existence) requires Enterprise Edition.
// These UNIQUE constraints are equivalent for Community Edition — existence
// is enforced by the Python ingestion pipeline rather than the database.

CREATE CONSTRAINT form_unique IF NOT EXISTS
    FOR (f:Form)
    REQUIRE (f.form_type, f.tax_year) IS UNIQUE;

CREATE CONSTRAINT form_line_unique IF NOT EXISTS
    FOR (fl:FormLine)
    REQUIRE (fl.form_type, fl.field_path, fl.tax_year) IS UNIQUE;

CREATE CONSTRAINT rule_unique IF NOT EXISTS
    FOR (r:Rule)
    REQUIRE (r.rule_id, r.tax_year, r.schema_version) IS UNIQUE;

CREATE CONSTRAINT error_code_unique IF NOT EXISTS
    FOR (e:ErrorCode)
    REQUIRE e.code IS UNIQUE;

// ─── Additional property indexes ──────────────────────────────────────────────

CREATE INDEX rule_severity_idx IF NOT EXISTS
    FOR (r:Rule) ON (r.severity, r.tax_year);

CREATE INDEX rule_type_idx IF NOT EXISTS
    FOR (r:Rule) ON (r.rule_type, r.tax_year);

CREATE INDEX form_family_idx IF NOT EXISTS
    FOR (r:Rule) ON (r.form_family, r.tax_year);

CREATE FULLTEXT INDEX rule_text_fulltext IF NOT EXISTS
    FOR (r:Rule) ON EACH [r.rule_text];

// =============================================================================
// Seed: Form nodes for 2024 individual return scope
// =============================================================================

MERGE (f:Form {form_type: '1040',    tax_year: 2024})
    SET f.form_title = 'U.S. Individual Income Tax Return',
        f.efile_schema_version = '5.2',
        f.instructions_url = 'https://www.irs.gov/instructions/i1040gi';

MERGE (f:Form {form_type: 'ScheduleA', tax_year: 2024})
    SET f.form_title = 'Itemized Deductions',
        f.instructions_url = 'https://www.irs.gov/instructions/i1040sca';

MERGE (f:Form {form_type: 'ScheduleB', tax_year: 2024})
    SET f.form_title = 'Interest and Ordinary Dividends',
        f.instructions_url = 'https://www.irs.gov/instructions/i1040sb';

MERGE (f:Form {form_type: 'ScheduleC', tax_year: 2024})
    SET f.form_title = 'Profit or Loss from Business (Sole Proprietorship)',
        f.instructions_url = 'https://www.irs.gov/instructions/i1040sc';

MERGE (f:Form {form_type: 'ScheduleD', tax_year: 2024})
    SET f.form_title = 'Capital Gains and Losses',
        f.instructions_url = 'https://www.irs.gov/instructions/i1040sd';

MERGE (f:Form {form_type: 'ScheduleE', tax_year: 2024})
    SET f.form_title = 'Supplemental Income and Loss',
        f.instructions_url = 'https://www.irs.gov/instructions/i1040se';

MERGE (f:Form {form_type: 'ScheduleSE', tax_year: 2024})
    SET f.form_title = 'Self-Employment Tax',
        f.instructions_url = 'https://www.irs.gov/instructions/i1040sse';

MERGE (f:Form {form_type: 'IRS6251', tax_year: 2024})
    SET f.form_title = 'Alternative Minimum Tax — Individuals',
        f.instructions_url = 'https://www.irs.gov/instructions/i6251';

MERGE (f:Form {form_type: 'IRS8960', tax_year: 2024})
    SET f.form_title = 'Net Investment Income Tax',
        f.instructions_url = 'https://www.irs.gov/instructions/i8960';

MERGE (f:Form {form_type: 'IRS8812', tax_year: 2024})
    SET f.form_title = 'Credits for Qualifying Children and Other Dependents',
        f.instructions_url = 'https://www.irs.gov/instructions/i8812';

MERGE (f:Form {form_type: 'IRS1116', tax_year: 2024})
    SET f.form_title = 'Foreign Tax Credit',
        f.instructions_url = 'https://www.irs.gov/instructions/i1116';

// =============================================================================
// Example Rule nodes and relationships
// (Full population done by the Python ingestion pipeline)
// =============================================================================

// ── F1040-041-01: SALT cap for MFJ/Single ────────────────────────────────────

MERGE (r:Rule {rule_id: 'F1040-041-01', tax_year: 2024, schema_version: '5.2'})
    SET r.rule_type       = 'DATABASE',
        r.form_family     = '1040',
        r.severity        = 'ERROR',
        r.error_code      = 'IND-041-01',
        r.rule_text       = 'SALT deduction limited to 10000 for MFJ Single and HOH filers',
        r.rule_expression = "If [FilingStatusCd] IN (1, 2, 4, 5) Then [StateLocalTaxDeductionAmt] <= 10000",
        r.parse_success   = true,
        r.is_current      = true;

MERGE (fl:FormLine {form_type: '1040', field_path: '//Return/ReturnData/IRS1040/StateLocalTaxDeductionAmt', tax_year: 2024})
    SET fl.label = 'State and Local Tax Deduction Amount',
        fl.short_field = 'StateLocalTaxDeductionAmt',
        fl.data_type = 'CURRENCY';

MERGE (ec:ErrorCode {code: 'IND-041-01'})
    SET ec.description = 'SALT cap violation — exceeds $10,000 limit';

MATCH  (r:Rule {rule_id: 'F1040-041-01', tax_year: 2024, schema_version: '5.2'})
MATCH  (fl:FormLine {form_type: '1040', field_path: '//Return/ReturnData/IRS1040/StateLocalTaxDeductionAmt', tax_year: 2024})
MATCH  (ec:ErrorCode {code: 'IND-041-01'})
MERGE  (fl)-[:GOVERNED_BY {severity: 'ERROR', rule_type: 'DATABASE'}]->(r)
MERGE  (r)-[:RAISES]->(ec);

// ── F1040-021-01: Form 8960 attachment requirement ────────────────────────────

MERGE (r:Rule {rule_id: 'F1040-021-01', tax_year: 2024, schema_version: '5.2'})
    SET r.rule_type       = 'REJECT',
        r.form_family     = '1040',
        r.severity        = 'ERROR',
        r.error_code      = 'IND-021-01',
        r.rule_text       = 'Form 8960 required when NIIT is greater than zero',
        r.rule_expression = "If [NetInvestmentIncomeTaxAmt] > 0 Then [IRS8960] must be attached",
        r.parse_success   = true,
        r.is_current      = true;

MERGE (fl8960:FormLine {form_type: '1040', field_path: '//Return/ReturnData/IRS8960', tax_year: 2024})
    SET fl8960.label = 'Form 8960 Attachment', fl8960.data_type = 'FORM';

MATCH (r:Rule {rule_id: 'F1040-021-01', tax_year: 2024, schema_version: '5.2'})
MATCH (f8960:Form {form_type: 'IRS8960', tax_year: 2024})
MERGE (r)-[:REQUIRES_ATTACHMENT]->(f8960);

// =============================================================================
// Relationship type reference (documentation — actual relationships
// created by Python ingestion pipeline)
// =============================================================================
//
// (:FormLine)-[:GOVERNED_BY  {severity, rule_type}]->(:Rule)
//   A field is subject to this validation rule.
//
// (:Rule)-[:CROSS_REFERENCES {field_role}]->(:FormLine)
//   A rule references a second field (source or target in the expression).
//
// (:Rule)-[:REQUIRES_ATTACHMENT]->(:Form)
//   Conditional: if rule fires, this form must be attached to the submission.
//
// (:Rule)-[:RAISES]->(:ErrorCode)
//   When this rule fires as a REJECT, this error code is returned in the NACK.
//
// (:Rule)-[:SUPERSEDES {changed_fields}]->(:Rule)
//   Newer schema version rule supersedes the older version's rule node.
//
// (:Rule)-[:YEAR_SUCCESSOR {delta_expression}]->(:Rule)
//   Same logical rule linking 2024 version to 2023 version.
//
// =============================================================================
