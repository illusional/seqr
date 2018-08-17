import React from 'react'
import PropTypes from 'prop-types'
import { Grid } from 'semantic-ui-react'

import ReduxFormWrapper from 'shared/components/form/ReduxFormWrapper'
import { QueryParamsEditor } from 'shared/components/QueryParamEditor'
import VariantSearchForm from './components/VariantSearchForm'
import VariantSearchResults from './components/VariantSearchResults'

const JSON_PARAMS = ['freqs', 'qualityFilter']

const jsonParsedQuery = query =>
  Object.entries(query).reduce((acc, [key, val]) => (
    { ...acc, [key]: (JSON_PARAMS.includes(key) ? JSON.parse(val) : val) }
  ), {})

const VariantSearch = ({ queryParams, updateQueryParams }) =>
  <Grid>
    <Grid.Row>
      <Grid.Column width={16}>
        <ReduxFormWrapper
          initialValues={jsonParsedQuery(queryParams)}
          onSubmit={updateQueryParams}
          form="variantSearch"
          submitButtonText="Search"
          noModal
          renderChildren={VariantSearchForm}
        />
      </Grid.Column>
    </Grid.Row>
    <VariantSearchResults search={queryParams} />
  </Grid>

VariantSearch.propTypes = {
  queryParams: PropTypes.object,
  updateQueryParams: PropTypes.func,
}

export default props => <QueryParamsEditor {...props}><VariantSearch /></QueryParamsEditor>
