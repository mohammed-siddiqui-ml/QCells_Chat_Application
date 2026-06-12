import { Box, Container, Typography } from '@mui/material'

function AdminPage() {
  return (
    <Container maxWidth="lg">
      <Box sx={{ mt: 4, mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Admin Dashboard
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Admin interface will be implemented here
        </Typography>
      </Box>
    </Container>
  )
}

export default AdminPage
