import React from 'react'
import { Table } from 'semantic-ui-react'
import PropTypes from 'prop-types'
import styled from 'styled-components'
import { connect } from 'react-redux'

import FamilyLayout from 'shared/components/panel/family/FamilyLayout'
import StateChangeForm from 'shared/components/form/StateChangeForm'
import { Dropdown, BaseSemanticInput } from 'shared/components/form/Inputs'

import { FAMILY_FIELD_NAME_LOOKUP } from 'shared/utils/constants'

import { getProjectAnalysisGroupFamiliesByGuid, getVisibleFamilies, getFamiliesTableState } from '../../../selectors'
import { updateFamiliesTable } from '../../../reducers'
import {
  CATEGORY_FAMILY_FILTERS,
  CASE_REVIEW_FAMILY_FILTER_OPTIONS,
  FAMILY_SORT_OPTIONS,
  CASE_REVIEW_TABLE_NAME,
} from '../../../constants'

import SortDirectionToggle from './SortDirectionToggle'

const RegularFontHeaderCell = styled(Table.HeaderCell)`
  font-weight: normal !important;
`

// Allows dropdowns to be visible inside table cell
const OverflowHeaderCell = styled(Table.HeaderCell)`
  overflow: visible !important;
  
  td {
     overflow: visible !important;
  }
`

const SpacedDropdown = styled(Dropdown)`
  padding-left: 10px;
  padding-right: 5px;
`

const FAMILY_SEARCH = {
  name: 'familiesSearch',
  component: BaseSemanticInput,
  inputType: 'Input',
  placeholder: 'Search...',
  inline: true,
  label: 'Search',
  labelHelp: 'Filter families by searching on family name or individual phenotypes',
}

const FAMILY_FILTER = {
  name: 'familiesFilter',
  component: SpacedDropdown,
  inline: true,
  fluid: false,
  selection: true,
  search: true,
  includeCategories: true,
  label: 'Filter',
}
const SORT_FILTER_FIELDS = [
  {
    name: 'familiesSortOrder',
    component: SpacedDropdown,
    inline: true,
    fluid: false,
    selection: true,
    label: 'Sort By',
    options: FAMILY_SORT_OPTIONS,
  },
  {
    name: 'familiesSortDirection',
    component: SortDirectionToggle,
  },
]
const FILTER_FIELDS = [FAMILY_SEARCH, ...SORT_FILTER_FIELDS]
const CASE_REVEIW_FILTER_FIELDS = [
  FAMILY_SEARCH, { ...FAMILY_FILTER, options: CASE_REVIEW_FAMILY_FILTER_OPTIONS }, ...SORT_FILTER_FIELDS,
]
const NESTED_FILTER_FIELD_NAME = 'nestedFamiliesFilter'

const mapFilterStateToProps = (state, ownProps) => ({
  nestedFilterState: getFamiliesTableState(state, ownProps)[NESTED_FILTER_FIELD_NAME],
})

const mapFilterDispatchToProps = (dispatch, ownProps) => ({
  updateNestedFilter: category => (value) => {
    console.log(category, value, ownProps.nestedFilterState)
    dispatch(updateFamiliesTable({
      [NESTED_FILTER_FIELD_NAME]: { ...(ownProps.nestedFilterState || {}), [category]: value },
    }, ownProps.tableName))
  },
})

const BaseFamilyTableFilter = ({ nestedFilterState, updateNestedFilter, category, options }) => (
  <Dropdown
    name={`${NESTED_FILTER_FIELD_NAME}.${category}`}
    value={(nestedFilterState || {})[category]}
    onChange={updateNestedFilter(category)}
    label={FAMILY_FIELD_NAME_LOOKUP[category]}
    options={options}
    inline
    multiple
  />
)

BaseFamilyTableFilter.propTypes = {
  nestedFilterState: PropTypes.object,
  updateNestedFilter: PropTypes.func.isRequired,
  category: PropTypes.string,
  options: PropTypes.arrayOf(PropTypes.object),
}

const FamilyTableFilter = connect(mapFilterStateToProps, mapFilterDispatchToProps)(BaseFamilyTableFilter)

const familyFieldDisplay = tableName => (field) => {
  const { id } = field
  return CATEGORY_FAMILY_FILTERS[id] ?
    <FamilyTableFilter tableName={tableName} category={id} options={CATEGORY_FAMILY_FILTERS[id]} /> :
    FAMILY_FIELD_NAME_LOOKUP[id]
}

const TableHeaderRow = React.memo(({
  visibleFamiliesCount, totalFamiliesCount, fields, tableName, familiesTableState, updateFamiliesTableField,
  showVariantDetails,
}) => (
  <Table.Header fullWidth>
    <Table.Row>
      <RegularFontHeaderCell width={5}>
        Showing &nbsp;
        {
          visibleFamiliesCount !== totalFamiliesCount ? (
            <span>
              <b>{visibleFamiliesCount}</b>
              &nbsp; out of &nbsp;
              <b>{totalFamiliesCount}</b>
            </span>
          ) : (
            <span>
              all &nbsp;
              <b>{totalFamiliesCount}</b>
            </span>
          )
        }
        &nbsp; families
      </RegularFontHeaderCell>
      <OverflowHeaderCell width={16} textAlign="right">
        <StateChangeForm
          initialValues={familiesTableState}
          updateField={updateFamiliesTableField}
          fields={(tableName === CASE_REVIEW_TABLE_NAME ? CASE_REVEIW_FILTER_FIELDS : FILTER_FIELDS)}
        />
      </OverflowHeaderCell>
    </Table.Row>
    {fields && (
      <Table.Row>
        <OverflowHeaderCell colSpan={2} textAlign="left">
          <FamilyLayout
            compact
            offset
            fields={fields}
            fieldDisplay={familyFieldDisplay(tableName)}
            rightContent={showVariantDetails ? 'Saved Variants' : null}
          />
        </OverflowHeaderCell>
      </Table.Row>
    )}
  </Table.Header>
))

TableHeaderRow.propTypes = {
  visibleFamiliesCount: PropTypes.number.isRequired,
  totalFamiliesCount: PropTypes.number.isRequired,
  familiesTableState: PropTypes.object.isRequired,
  updateFamiliesTableField: PropTypes.func.isRequired,
  fields: PropTypes.arrayOf(PropTypes.object),
  tableName: PropTypes.string,
  showVariantDetails: PropTypes.bool,
}

export { TableHeaderRow as TableHeaderRowComponent }

const mapStateToProps = (state, ownProps) => ({
  visibleFamiliesCount: getVisibleFamilies(state, ownProps).length,
  totalFamiliesCount: Object.keys(getProjectAnalysisGroupFamiliesByGuid(state, ownProps)).length,
  familiesTableState: getFamiliesTableState(state, ownProps),
})

const mapDispatchToProps = (dispatch, ownProps) => ({
  updateFamiliesTableField: field => (value) => {
    dispatch(updateFamiliesTable({ [field]: value }, ownProps.tableName))
  },
})

export default connect(mapStateToProps, mapDispatchToProps)(TableHeaderRow)
